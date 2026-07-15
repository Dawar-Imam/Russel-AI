"""Redis-backed distributed lock preventing pregenerate_interview_questions()
(app/services/question_pregeneration_service.py) and generate_interview_questions()
(app/services/interview_service.py) from both writing questions for the same
interview_id when they race (candidate clicks through while the background
Celery pre-generation task is still mid-LLM-call). Redis is already the Celery
broker, reused here as a cheap distributed lock — no schema change.

Deliberately has zero dependency on interview_service.py or
question_pregeneration_service.py — both of those import from here, not the
reverse, so this module can never be part of an import cycle.

Wait timeout is 25s, not the LLM call itself's typical duration (single
question-generation call is comparable to the ~17s ATS LLM call measured in
Ticket 4) — an 8s wait would routinely time out mid-generation and defeat
the point. If Redis itself is unreachable, every helper below fails open
(treats the lock as acquired/released) rather than raising — this is a
latency optimization, not a hard dependency; it must never break the live
on-click generation path just because Redis is down.
"""
import logging

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
PREGEN_LOCK_TTL_SECONDS = 30
PREGEN_LOCK_WAIT_TIMEOUT_SECONDS = 25.0
PREGEN_LOCK_POLL_INTERVAL_SECONDS = 0.5


def pregen_lock_key(interview_id: str) -> str:
    return f"pregen_lock:{interview_id}"


def acquire_pregen_lock(interview_id: str) -> bool:
    try:
        return bool(_redis_client.set(pregen_lock_key(interview_id), "1", nx=True, ex=PREGEN_LOCK_TTL_SECONDS))
    except redis.RedisError:
        logger.warning(
            "pregen lock: Redis unreachable acquiring lock for interview_id=%s — failing open (proceeding unlocked)",
            interview_id,
        )
        return True


def release_pregen_lock(interview_id: str) -> None:
    try:
        _redis_client.delete(pregen_lock_key(interview_id))
    except redis.RedisError:
        logger.warning("pregen lock: Redis unreachable releasing lock for interview_id=%s — ignoring", interview_id)
