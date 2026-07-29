import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="interview_scheduling.run_scheduled_interview")
def run_scheduled_interview_task(interview_id: str, join_window_minutes: float | None = None) -> None:
    """Fired via Celery's `eta` at an interview's scheduled local time — one task per
    scheduled interview, dispatched the moment it's (re)scheduled (see
    scheduling_service._dispatch_schedule_task), not a periodic sweep. Blocks this
    worker for the candidate join-wait window and, if they show up, the full interview
    duration — see room_connection.start_scheduled_interview's docstring for why this
    is a plain await rather than fire-and-forget.

    `join_window_minutes` is a debugging/test-only override (see
    room_connection.start_scheduled_interview) — real ETA dispatch never passes it, so
    production behavior is unaffected."""
    from app.ai.voice_agent.room_connection import start_scheduled_interview

    logger.info("interview_scheduling_tasks: task received (ETA reached) for interview=%s", interview_id)
    try:
        asyncio.run(start_scheduled_interview(interview_id, join_window_minutes=join_window_minutes))
        logger.info("interview_scheduling_tasks: run_scheduled_interview completed for interview=%s", interview_id)
    except Exception:
        logger.exception(
            "interview_scheduling_tasks: run_scheduled_interview FAILED for interview=%s", interview_id
        )
        raise
