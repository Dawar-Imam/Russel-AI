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


# ---------------------------------------------------------------------------
# Rerun "generation" tracking — lets a newer recruiter-triggered rerun batch
# supersede an older one that's still retrying, per application, without a second
# distributed lock. See ats_rerun_tasks._run_one_application (the consumer) and
# job_service.rerun_ats_for_job (the producer, called once per dispatched batch).
# ---------------------------------------------------------------------------

_RERUN_GENERATION_TTL_SECONDS = 1800  # generous — long enough to outlast a full batch + retries


def rerun_generation_key(application_id: str) -> str:
    return f"ats_rerun_gen:{application_id}"


def set_latest_rerun_generation_batch(application_ids: list[str], rerun_id: str) -> None:
    """Marks `rerun_id` as the current desired ATS-rerun version for every id in
    `application_ids` — called once per dispatched batch, right before
    ats_rerun_tasks.run_batch.delay(). Pipelined into a single Redis round-trip so this
    stays fast regardless of batch size (rerun_ats_for_job must still return immediately).

    Any in-flight or retry-waiting thread for an OLDER rerun_id for the same
    application_id checks this before each attempt (is_latest_rerun_generation) and
    stops immediately if superseded, so re-clicking "Rerun ATS" while a previous batch
    is still processing an application cancels that stale pending retry instead of both
    eventually executing.
    """
    if not application_ids:
        return
    try:
        pipe = _redis_client.pipeline(transaction=False)
        for application_id in application_ids:
            pipe.set(rerun_generation_key(application_id), rerun_id, ex=_RERUN_GENERATION_TTL_SECONDS)
        pipe.execute()
    except redis.RedisError:
        logger.warning(
            "ats lock: Redis unreachable setting rerun generation for %d application(s) — "
            "duplicate-rerun suppression disabled for this dispatch",
            len(application_ids),
        )


def is_latest_rerun_generation(application_id: str, rerun_id: str) -> bool:
    """True if `rerun_id` is still the most recently dispatched rerun for this
    application (see set_latest_rerun_generation_batch) — used by
    ats_rerun_tasks._run_one_application to detect it has been superseded by a newer
    "Rerun ATS" request and should stop retrying. Fails open (True) on a Redis outage or
    a missing key (TTL expired, or Redis was unreachable when the generation was set) so
    a real rerun is never silently skipped because of this best-effort dedup layer."""
    try:
        current = _redis_client.get(rerun_generation_key(application_id))
    except redis.RedisError:
        return True
    if current is None:
        return True
    return (current.decode() if isinstance(current, bytes) else current) == rerun_id
