"""Redis-backed distributed lock preventing more than one ATS run (original apply-time
run or a recruiter-triggered rerun) from writing `Applications.ats_details` for the same
application_id concurrently.

Same shape as app/services/pregen_lock.py (same Redis instance, same fail-open behavior
if Redis is unreachable) — kept as its own module rather than imported from pregen_lock.py
so an ATS-run lock timeout can never be confused with, or block on, a question-generation
lock for the same interview.
"""
import logging

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
ATS_LOCK_TTL_SECONDS = 60


def ats_lock_key(application_id: str) -> str:
    return f"ats_lock:{application_id}"


def acquire_ats_lock(application_id: str) -> bool:
    try:
        return bool(_redis_client.set(ats_lock_key(application_id), "1", nx=True, ex=ATS_LOCK_TTL_SECONDS))
    except redis.RedisError:
        logger.warning(
            "ats lock: Redis unreachable acquiring lock for application_id=%s — failing open (proceeding unlocked)",
            application_id,
        )
        return True


def release_ats_lock(application_id: str) -> None:
    try:
        _redis_client.delete(ats_lock_key(application_id))
    except redis.RedisError:
        logger.warning("ats lock: Redis unreachable releasing lock for application_id=%s — ignoring", application_id)


def get_redis_client() -> redis.Redis:
    """Shared client, reused by job_service.py to track in-flight ATS-rerun batches
    (see ats_rerun_batch_key) — same Redis instance as the lock above, just a different
    key namespace, so no second connection is needed."""
    return _redis_client


def ats_rerun_batch_key(job_id: str) -> str:
    return f"ats_rerun_batch:{job_id}"
