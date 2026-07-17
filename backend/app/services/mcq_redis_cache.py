"""Redis-backed per-job cache of recently used MCQ option orderings.

Ticket: "As the system, I want to randomise MCQ option order for each
candidate so that answer patterns cannot be shared between candidates."

Each job posting gets its own Redis list (key `mcq_queue:<job_id>`), capped to
MCQ_QUEUE_MAX_LEN entries via LTRIM, holding a signature of the last few
(question_text, shuffled-option-order) pairs handed out for that job.
shuffle_mcq_options() uses it to avoid re-serving an identical ordering to the
next few candidates for the same job — best-effort, not a hard guarantee.

Same Redis instance as ats_lock.py / pregen_lock.py (get_redis_client()) — no
new connection. Every operation here is best-effort: a Redis failure is
caught and logged, and shuffle_mcq_options() always still returns a shuffled
list (falling back to a plain in-process shuffle with no cross-candidate
dedup) so a Redis outage can never block question generation.

Correctness note: `correct_option` is stored as the literal option text (see
app.ai.interview_tools.schemas.QuestionItem), not an index — so shuffling the
`options` list here never requires remapping the correct answer; grading
already matches by value.
"""
import json
import logging
import random
from typing import TYPE_CHECKING

import redis

from app.services.ats_lock import get_redis_client

if TYPE_CHECKING:
    from app.ai.interview_tools.schemas import QuestionItem

logger = logging.getLogger(__name__)

MCQ_QUEUE_MAX_LEN = 5
_QUEUE_KEY_PREFIX = "mcq_queue:"
_SHUFFLE_MAX_ATTEMPTS = 5


def mcq_queue_key(job_id: str) -> str:
    return f"{_QUEUE_KEY_PREFIX}{job_id}"


def _signature(question_text: str, options: list[str]) -> str:
    return json.dumps({"q": question_text, "o": options}, sort_keys=True)


def get_queued_orderings(job_id: str) -> list[dict]:
    """Return the job's currently-queued (question_text, options) pairs, most
    recent first — used by question_pregeneration_service to pass "orderings
    already served for this job" to the LLM prompt so it can avoid repeating
    them. Best-effort: returns [] on a Redis outage, same as the rest of this
    module."""
    try:
        client = get_redis_client()
        raw = client.lrange(mcq_queue_key(job_id), 0, MCQ_QUEUE_MAX_LEN - 1)
    except redis.RedisError:
        logger.warning(
            "mcq_redis_cache: Redis unreachable reading queue for job_id=%s", job_id
        )
        return []

    entries = []
    for r in raw:
        try:
            decoded = json.loads(r.decode() if isinstance(r, bytes) else r)
            entries.append({"question_text": decoded["q"], "options": decoded["o"]})
        except (json.JSONDecodeError, KeyError):
            continue
    return entries


def mcq_orderings_match_queue(job_id: str, questions: list["QuestionItem"]) -> bool:
    """True if any MCQ in `questions` has the exact same (question_text, options
    order) as an entry already queued for this job — used by
    question_pregeneration_service to decide whether a freshly generated batch
    needs to be retried. Best-effort: a Redis outage is treated as "no match"
    so it can never block generation."""
    try:
        client = get_redis_client()
        recent_raw = client.lrange(mcq_queue_key(job_id), 0, MCQ_QUEUE_MAX_LEN - 1)
        recent = {r.decode() if isinstance(r, bytes) else r for r in recent_raw}
    except redis.RedisError:
        logger.warning(
            "mcq_redis_cache: Redis unreachable checking queue for job_id=%s", job_id
        )
        return False

    for q in questions:
        if q.question_type == "mcq" and q.options:
            if _signature(q.question_text, q.options) in recent:
                return True
    return False


def push_generated_mcqs(job_id: str, questions: list["QuestionItem"]) -> None:
    """Push every MCQ in `questions` onto the job's queue (most recent first),
    trimmed to MCQ_QUEUE_MAX_LEN — called by question_pregeneration_service
    right after a generation batch is accepted, so later generations/shuffles
    for this job see it as "recently used". Best-effort, Redis outage is
    logged and swallowed."""
    mcqs = [q for q in questions if q.question_type == "mcq" and q.options]
    if not mcqs:
        return
    try:
        client = get_redis_client()
        key = mcq_queue_key(job_id)
        for q in mcqs:
            client.lpush(key, _signature(q.question_text, q.options))
        client.ltrim(key, 0, MCQ_QUEUE_MAX_LEN - 1)
    except redis.RedisError:
        logger.warning(
            "mcq_redis_cache: Redis unreachable pushing generated MCQs for job_id=%s", job_id
        )


def init_job_queue(job_id: str) -> None:
    """Called when a job posting is created. Redis lists are created lazily on
    first push, so this just guarantees a fresh, empty queue for the job_id —
    an explicit lifecycle hook matching the ticket's "initialize its own Redis
    queue", not a functional requirement (job_ids are UUIDs, so a stale queue
    from an ID collision is not a realistic concern)."""
    try:
        get_redis_client().delete(mcq_queue_key(job_id))
    except redis.RedisError:
        logger.warning(
            "mcq_redis_cache: Redis unreachable initializing queue for job_id=%s", job_id
        )


def clear_job_queue(job_id: str) -> None:
    """Called when a job is inactivated — deletes all cached MCQ ordering data
    for it so no stale MCQ data remains in Redis for inactive jobs."""
    try:
        get_redis_client().delete(mcq_queue_key(job_id))
    except redis.RedisError:
        logger.warning(
            "mcq_redis_cache: Redis unreachable clearing queue for job_id=%s", job_id
        )


def shuffle_mcq_options(job_id: str, question_text: str, options: list[str]) -> list[str]:
    """Return a shuffled copy of `options` for one candidate's MCQ.

    Best-effort avoids repeating an exact ordering used in one of this job's
    last MCQ_QUEUE_MAX_LEN generations. Falls back to a plain in-process
    shuffle (no cross-candidate dedup) if Redis is unreachable or the option
    list has fewer than 2 entries to reorder.
    """
    shuffled = list(options)
    if len(shuffled) < 2:
        return shuffled

    try:
        client = get_redis_client()
        key = mcq_queue_key(job_id)
        recent_raw = client.lrange(key, 0, MCQ_QUEUE_MAX_LEN - 1)
        recent = {r.decode() if isinstance(r, bytes) else r for r in recent_raw}

        for _ in range(_SHUFFLE_MAX_ATTEMPTS):
            random.shuffle(shuffled)
            if _signature(question_text, shuffled) not in recent:
                break

        client.lpush(key, _signature(question_text, shuffled))
        client.ltrim(key, 0, MCQ_QUEUE_MAX_LEN - 1)
    except redis.RedisError:
        logger.warning(
            "mcq_redis_cache: Redis unreachable shuffling MCQ for job_id=%s — "
            "using a plain shuffle with no cross-candidate dedup",
            job_id,
        )
        random.shuffle(shuffled)

    return shuffled
