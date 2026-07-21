import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.celery_app import celery_app
from app.services.application_service import RerunOutcome, rerun_ats_and_persist
from app.services.ats_lock import is_latest_rerun_generation

logger = logging.getLogger(__name__)

# Retryable outcomes: LOCK_CONTENDED (another run holds the per-application Redis lock —
# see app.services.ats_lock, ATS_LOCK_TTL_SECONDS=60), TRANSIENT_ERROR (DB/network/LLM-API
# error before any write committed), and VALIDATION_FAILED (the LLM returned malformed/
# unusable structured output — worth a couple of retries since it's often a one-off model
# hiccup, not a persistent condition). EXCLUDED/NOT_FOUND are intentional skips and finish
# normally. rerun_ats_and_persist only ever returns TRANSIENT_ERROR/VALIDATION_FAILED for
# failures before its persistence write commits, so retrying here can never duplicate a
# persisted rerun result — and on final exhaustion, "leave the prior ats_details/status
# untouched" (already rerun_ats_and_persist's behavior on every failed attempt) *is* the
# existing fallback flow; there is nothing further to trigger.
_RETRYABLE_OUTCOMES = (RerunOutcome.LOCK_CONTENDED, RerunOutcome.TRANSIENT_ERROR, RerunOutcome.VALIDATION_FAILED)
_RETRY_COUNTDOWN_SECONDS = 10
_MAX_ATTEMPTS_PER_APPLICATION = 3

# Upper bound on how many applications are re-screened concurrently within one batch.
# Celery itself is expected to run as a single --pool=solo worker (see app/celery_app.py's
# OPENBLAS_NUM_THREADS note — this codebase already targets solo on Windows); this
# ThreadPoolExecutor, not Celery worker/task concurrency, is what parallelizes reruns
# across applications.
_MAX_BATCH_WORKERS = 8


def _run_one_application(application_id: str, recruiter_id: str | None, rerun_id: str | None) -> RerunOutcome:
    """Runs the full rerun for one application (its own event loop, via asyncio.run) —
    submitted as one ThreadPoolExecutor job per application by run_batch below. Retries
    on lock contention / transient / validation errors up to
    _MAX_ATTEMPTS_PER_APPLICATION times.

    Previously this bounded retry was implemented via Celery's `self.retry()` on a
    per-application task (the old ats_rerun_tasks.run_single). Under --pool=solo with a
    single batch task doing its own in-process fan-out, there is no per-application
    Celery task to rebind a retry onto, so the same bounded-retry policy is replicated
    here as a plain loop + sleep instead — the sleep only blocks this one worker thread,
    not the batch or other applications' threads.

    An exception escaping rerun_ats_and_persist itself (a "thread execution failure" —
    e.g. an unexpected bug, not one of its own classified outcomes) is treated the same
    as TRANSIENT_ERROR and retried the same bounded number of times.

    `rerun_id`, if given, is this application's generation token as of when the
    containing batch was dispatched (see app.services.ats_lock.
    set_latest_rerun_generation_batch, written by job_service.rerun_ats_for_job right
    before dispatch). Checked before every attempt — including the first — so a
    recruiter re-triggering "Rerun ATS" for the same job while this application's rerun
    is still pending/retrying cancels this stale attempt instead of letting both
    eventually execute: the newer batch's own thread for this application_id will run
    (and win) instead. `rerun_id=None` disables this check (nothing to compare against).
    """
    outcome = RerunOutcome.TRANSIENT_ERROR
    for attempt in range(1, _MAX_ATTEMPTS_PER_APPLICATION + 1):
        if rerun_id is not None and not is_latest_rerun_generation(application_id, rerun_id):
            logger.info(
                "ats_rerun_tasks.run_batch: application_id=%s superseded by a newer rerun "
                "request — abandoning (attempt %d/%d)",
                application_id, attempt, _MAX_ATTEMPTS_PER_APPLICATION,
            )
            return RerunOutcome.SUPERSEDED

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
        "ats_rerun_tasks.run_batch: application_id=%s exhausted %d attempts (final outcome=%s) — "
        "prior ats_details/status left untouched (existing fallback)",
        application_id, _MAX_ATTEMPTS_PER_APPLICATION, outcome,
    )
    return outcome


@celery_app.task(name="ats_rerun_tasks.run_batch")
def run_batch(application_ids: list[str], recruiter_id: str | None = None, rerun_id: str | None = None) -> None:
    """Recruiter-triggered ATS rerun entry point — see job_service.rerun_ats_for_job,
    which dispatches this ONE task per job-scoped rerun request (not one task per
    application, as the old run_single did) and returns to the caller immediately,
    without waiting for this task, its ThreadPoolExecutor fan-out, or any retry to
    complete — progress is tracked separately via job_service.get_ats_rerun_status.

    Celery's role here is purely scheduling/queueing this single task; it is designed to
    run under `celery -A app.celery_app worker --pool=solo` (one worker process, no
    Celery-level concurrency). All parallelism across applications comes from the
    ThreadPoolExecutor created below — one thread per application (bounded by
    _MAX_BATCH_WORKERS), each running the same rerun_ats_and_persist logic, Redis lock
    (app.services.ats_lock), and retry policy (_run_one_application) as before the
    switch away from per-application Celery tasks. A single application raising or
    exhausting its retries is logged and does not stop or delay the rest of the batch —
    each future's result/exception is handled independently in the as_completed loop.

    `rerun_id` (see app.services.ats_lock.set_latest_rerun_generation_batch) lets each
    application's thread detect it has been superseded by a newer "Rerun ATS" request
    dispatched after this one, for the same application_id.
    """
    count = len(application_ids)
    if count == 0:
        logger.info("ats_rerun_tasks.run_batch: called with an empty application_ids list — nothing to do")
        return

    max_workers = count
    logger.info(
        "ats_rerun_tasks.run_batch: starting batch of %d application(s), max_workers=%d, rerun_id=%s",
        count, max_workers, rerun_id,
    )

    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ats-rerun-batch")
    try:
        future_to_application = {
            executor.submit(_run_one_application, application_id, recruiter_id, rerun_id): application_id
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
