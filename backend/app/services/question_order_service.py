"""Redis-backed per-round dedup of question order and MCQ option order.

Ticket: "As the system, I want to randomise question order and MCQ option
order for each candidate so that answer patterns cannot be shared between
candidates."

Per-`interview_round_id` Redis list (key `round_question_queue:<interview_round_id>`),
capped at MAX_HISTORY_ENTRIES, holding the last few candidates' final
{question_order, mcq_options} for that round — the queue only ever holds
question text and option order, never candidate_answer/score, which stay in
SQL (InterviewQuestions) exactly as before.

Same Redis instance as ats_lock.py / pregen_lock.py (get_redis_client()) — no
new connection. Every operation here is best-effort, matching this codebase's
established Redis-dedup convention (the old job_posting_id-scoped
mcq_redis_cache.py never locked its LPUSH/LTRIM either): a Redis outage is
caught and logged, dedupe_order_and_options() always still returns a valid
(possibly unshuffled) item list so it can never block question generation,
and record_round_history() silently no-ops on failure.

Both generation call sites — question_pregeneration_service (background) and
interview_service.generate_interview_questions (live) — call
dedupe_order_and_options() right after the LLM returns a batch and before
persisting it to SQL, then call record_round_history() once that SQL write
has committed (mirrors the old push_generated_mcqs-after-commit ordering).
"""
import json
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import redis

from app.services.ats_lock import get_redis_client

if TYPE_CHECKING:
    from app.ai.interview_tools.schemas import QuestionItem as AIQuestionItem

logger = logging.getLogger(__name__)

MAX_HISTORY_ENTRIES = 5
MAX_ORDER_SHUFFLE_ATTEMPTS = 10
MAX_OPTION_SHUFFLE_ATTEMPTS = 5
_QUEUE_KEY_PREFIX = "round_question_queue:"


def round_queue_key(interview_round_id: str) -> str:
    return f"{_QUEUE_KEY_PREFIX}{interview_round_id}"


def _load_history(interview_round_id: str) -> list[dict]:
    """Best-effort: returns [] on a Redis outage or malformed entries, same as
    the rest of this module — a Redis problem must never block generation."""
    try:
        client = get_redis_client()
        raw = client.lrange(round_queue_key(interview_round_id), 0, MAX_HISTORY_ENTRIES - 1)
    except redis.RedisError:
        logger.warning(
            "question_order_service: Redis unreachable reading history for interview_round_id=%s",
            interview_round_id,
        )
        return []

    history = []
    for r in raw:
        try:
            history.append(json.loads(r.decode() if isinstance(r, bytes) else r))
        except (TypeError, ValueError):
            continue
    return history


def _question_order_collides(question_texts: list[str], history: list[dict]) -> bool:
    return any(entry.get("question_order") == question_texts for entry in history)


def _mcq_options_collide(question_text: str, options: list[str], history: list[dict]) -> bool:
    return any(
        entry.get("mcq_options", {}).get(question_text) == options for entry in history
    )


def _shuffle_question_order(
    interview_round_id: str, items: list["AIQuestionItem"], history: list[dict]
) -> None:
    """Reorders `items` in place. Split out of dedupe_order_and_options so it can run
    concurrently with _shuffle_mcq_options (see there)."""
    for attempt in range(MAX_ORDER_SHUFFLE_ATTEMPTS):
        question_texts = [item.question_text for item in items]
        if not _question_order_collides(question_texts, history):
            break
        random.shuffle(items)
    else:
        logger.warning(
            "question_order_service: exhausted %d question-order shuffle attempts for "
            "interview_round_id=%s, proceeding with last shuffle",
            MAX_ORDER_SHUFFLE_ATTEMPTS, interview_round_id,
        )


def _shuffle_mcq_options(
    interview_round_id: str, items: list["AIQuestionItem"], history: list[dict]
) -> None:
    """Shuffles each MCQ item's own .options in place. Takes its own copy of `items`
    (see dedupe_order_and_options' call site) so iterating here is never disturbed by
    _shuffle_question_order concurrently reordering the original list — the two never
    touch the same piece of shared state (list order vs. an item's own attribute), so no
    lock is needed."""
    for item in items:
        if item.question_type != "mcq" or not item.options or len(item.options) < 2:
            continue
        for attempt in range(MAX_OPTION_SHUFFLE_ATTEMPTS):
            if not _mcq_options_collide(item.question_text, item.options, history):
                break
            random.shuffle(item.options)
        else:
            logger.warning(
                "question_order_service: exhausted %d option shuffle attempts for "
                "question_text=%r in interview_round_id=%s, proceeding with last shuffle",
                MAX_OPTION_SHUFFLE_ATTEMPTS, item.question_text, interview_round_id,
            )


def dedupe_order_and_options(
    interview_round_id: str, items: list["AIQuestionItem"]
) -> list["AIQuestionItem"]:
    """Randomises `items`' order and each MCQ's option order until neither
    collides with one of the round's last MAX_HISTORY_ENTRIES candidates
    (read from Redis). Does not itself write anything — call
    record_round_history() once the caller's SQL write has committed.

    Question-order shuffling and MCQ-option shuffling are independent (one reorders the
    list container, the other mutates each item's own .options), so they run
    concurrently on two threads — _shuffle_mcq_options is handed its own shallow copy of
    `items` so its iteration can't be disturbed by the other thread reordering the
    original list mid-loop.

    Mutates and returns `items` (order and option lists are shuffled in place).
    """
    history = _load_history(interview_round_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        order_future = executor.submit(_shuffle_question_order, interview_round_id, items, history)
        options_future = executor.submit(_shuffle_mcq_options, interview_round_id, items[:], history)
        order_future.result()
        options_future.result()

    return items


def record_round_history(interview_round_id: str, items: list["AIQuestionItem"]) -> None:
    """Pushes this candidate's final {question_order, mcq_options} onto the
    round's queue (most recent first), trimmed to MAX_HISTORY_ENTRIES — call
    once the SQL write persisting `items` has committed. Best-effort: a Redis
    outage is logged and swallowed, same as the rest of this module."""
    entry = {
        "question_order": [item.question_text for item in items],
        "mcq_options": {
            item.question_text: item.options
            for item in items
            if item.question_type == "mcq" and item.options
        },
    }
    try:
        client = get_redis_client()
        key = round_queue_key(interview_round_id)
        client.lpush(key, json.dumps(entry))
        client.ltrim(key, 0, MAX_HISTORY_ENTRIES - 1)
    except redis.RedisError:
        logger.warning(
            "question_order_service: Redis unreachable recording history for interview_round_id=%s",
            interview_round_id,
        )
