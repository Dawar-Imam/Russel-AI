import asyncio
import logging

from app.celery_app import celery_app
from app.services.application_service import rerun_ats_and_persist

logger = logging.getLogger(__name__)


@celery_app.task(name="ats_rerun_tasks.run_single")
def run_single(application_id: str, recruiter_id: str | None = None) -> None:
    """Re-run ATS for one application on a recruiter's explicit request (see
    job_service.select_applications_for_ats_rerun, which dispatches one of these per
    selected application_id). Unlike written_test_tasks.trigger, a failure here is worth
    surfacing loudly — rerun_ats_and_persist already leaves the application's prior
    ats_details/status untouched on LLM failure, so there's no data-corruption risk, but
    the recruiter should be able to tell from logs why a candidate wasn't re-screened.
    """
    try:
        asyncio.run(rerun_ats_and_persist(application_id, recruiter_id))
    except Exception:
        logger.exception("ats_rerun_tasks.run_single: rerun failed for application_id=%s", application_id)
