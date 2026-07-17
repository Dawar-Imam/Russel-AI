import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.celery_app import celery_app
from app.services.application_service import RerunOutcome, rerun_ats_and_persist

logger = logging.getLogger(__name__)

# Retryable outcomes: LOCK_CONTENDED (another run holds the per-application Redis lock —
# see app.services.ats_lock, ATS_LOCK_TTL_SECONDS=60) and TRANSIENT_ERROR (DB/LLM error
# before any write committed). EXCLUDED/VALIDATION_FAILED/NOT_FOUND are intentional skips
# and finish normally. rerun_ats_and_persist only ever returns TRANSIENT_ERROR for
# failures before its persistence write commits, so retrying here can never duplicate a
# persisted rerun result.
_RETRYABLE_OUTCOMES = (RerunOutcome.LOCK_CONTENDED, RerunOutcome.TRANSIENT_ERROR)
_RETRY_COUNTDOWN_SECONDS = 10
_MAX_ATTEMPTS_PER_APPLICATION = 4

# Upper bound on how many applications are re-screened concurrently within one batch.
# Celery itself is expected to run as a single --pool=solo worker (see app/celery_app.py's
# OPENBLAS_NUM_THREADS note — this codebase already targets solo on Windows); this
# ThreadPoolExecutor, not Celery worker/task concurrency, is what parallelizes reruns
# across applications.
_MAX_BATCH_WORKERS = 8


def _run_one_application(application_id: str, recruiter_id: str | None) -> RerunOutcome:
    """Runs the full rerun for one application (its own event loop, via asyncio.run) —
    submitted as one ThreadPoolExecutor job per application by run_batch below. Retries
    on lock contention / transient errors up to _MAX_ATTEMPTS_PER_APPLICATION times.

    Previously this bounded retry was implemented via Celery's `self.retry()` on a
    per-application task (the old ats_rerun_tasks.run_single). Under --pool=solo with a
    single batch task doing its own in-process fan-out, there is no per-application
    Celery task to rebind a retry onto, so the same bounded-retry policy is replicated
    here as a plain loop + sleep instead — the sleep only blocks this one worker thread,
    not the batch or other applications' threads.

    An exception escaping rerun_ats_and_persist itself is treated the same as
    TRANSIENT_ERROR: rerun_ats_and_persist only ever returns TRANSIENT_ERROR for failures
    before its persistence write commits, so treating an unexpected crash the same way
    (retry, bounded) can never duplicate a persisted result either.
    """
    outcome = RerunOutcome.TRANSIENT_ERROR
    for attempt in range(1, _MAX_ATTEMPTS_PER_APPLICATION + 1):
        try:
            outcome = asyncio.run(rerun_ats_and_persist(application_id, recruiter_id))
        except Exception:
            logger.exception(
                "ats_rerun_tasks.run_batch: unexpected failure for application_id=%s (attempt %d/%d)",
                application_id, attempt, _MAX_ATTEMPTS_PER_APPLICATION,
            )
            outcome = RerunOutcome.TRANSIENT_ERROR

        if outcome not in _RETRYABLE_OUTCOMES:
            return outcome

        if attempt < _MAX_ATTEMPTS_PER_APPLICATION:
            logger.warning(
                "ats_rerun_tasks.run_batch: retrying application_id=%s in %ds (attempt %d/%d, outcome=%s)",
                application_id, _RETRY_COUNTDOWN_SECONDS, attempt + 1, _MAX_ATTEMPTS_PER_APPLICATION, outcome,
            )
            time.sleep(_RETRY_COUNTDOWN_SECONDS)

    logger.error(
        "ats_rerun_tasks.run_batch: application_id=%s exhausted %d attempts (final outcome=%s)",
        application_id, _MAX_ATTEMPTS_PER_APPLICATION, outcome,
    )
    return outcome


@celery_app.task(name="ats_rerun_tasks.run_batch")
def run_batch(application_ids: list[str], recruiter_id: str | None = None) -> None:
    """Recruiter-triggered ATS rerun entry point — see job_service.rerun_ats_for_job,
    which dispatches this ONE task per job-scoped rerun request (not one task per
    application, as the old run_single did). Celery's role here is purely
    scheduling/queueing this single task; it is designed to run under
    `celery -A app.celery_app worker --pool=solo` (one worker process, no Celery-level
    concurrency). All parallelism across applications comes from the ThreadPoolExecutor
    created below — one thread per application (bounded by _MAX_BATCH_WORKERS), each
    running the same rerun_ats_and_persist logic, Redis lock (app.services.ats_lock), and
    retry policy (_run_one_application) as before the switch away from per-application
    Celery tasks. A single application raising or exhausting its retries is logged and
    does not stop or delay the rest of the batch — each future's result/exception is
    handled independently in the as_completed loop.
    """
    count = len(application_ids)
    if count == 0:
        logger.info("ats_rerun_tasks.run_batch: called with an empty application_ids list — nothing to do")
        return

    max_workers = min(count, _MAX_BATCH_WORKERS)
    logger.info(
        "ats_rerun_tasks.run_batch: starting batch of %d application(s), max_workers=%d",
        count, max_workers,
    )

    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ats-rerun-batch")
    try:
        future_to_application = {
            executor.submit(_run_one_application, application_id, recruiter_id): application_id
            for application_id in application_ids
        }
        for future in as_completed(future_to_application):
            application_id = future_to_application[future]
            try:
                outcome = future.result()
                logger.info(
                    "ats_rerun_tasks.run_batch: application_id=%s finished (outcome=%s)",
                    application_id, outcome,
                )
            except Exception:
                # _run_one_application already catches everything rerun_ats_and_persist can
                # raise — this only guards against something escaping _run_one_application
                # itself, so one such failure still can't take down the rest of the batch.
                logger.exception(
                    "ats_rerun_tasks.run_batch: application_id=%s raised unexpectedly", application_id
                )
    finally:
        executor.shutdown(wait=True)

    logger.info("ats_rerun_tasks.run_batch: finished batch of %d application(s)", count)
