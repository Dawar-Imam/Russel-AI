import asyncio
import logging

from app.celery_app import celery_app
from app.services.question_pregeneration_service import pregenerate_interview_questions

logger = logging.getLogger(__name__)


@celery_app.task(name="written_test_tasks.trigger")
def trigger(interview_id: str) -> None:
    """Pre-generate and persist a round's interview questions in the background,
    fired right after ATS passes (first round — application_service.py) or a prior
    round is scored Pass (next round — interview_service._save_scores_and_complete).

    Fully best-effort, single attempt, no retry (see question_pregeneration_service.
    pregenerate_interview_questions for the skip conditions — oral/voice rounds,
    already-generated rounds). Any failure here is caught and logged, never raised: the live
    generate_interview_questions() endpoint still generates on-demand as a fallback
    if this hasn't run yet or failed, so a failure here has zero effect on the
    candidate's ability to start the interview — it just loses the latency win.
    """
    try:
        asyncio.run(_run(interview_id))
    except Exception:
        logger.exception(
            "written_test_tasks.trigger: pre-generation failed for interview_id=%s "
            "(non-fatal — live generate_interview_questions fallback still applies)",
            interview_id,
        )


async def _run(interview_id: str) -> None:
    await pregenerate_interview_questions(interview_id)
