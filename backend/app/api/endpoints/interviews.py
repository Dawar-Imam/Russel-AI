from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.ai.voice_agent.room_connection import (
    CreateRoomResponse,
    conduct_voice_interview,
    signal_interview_done,
    wait_for_interview_done,
)
from app.core.config import settings
from app.schemas.interviews import (
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    ScoreAnswersRequest,
    ScoreAnswersResponse,
)
from app.services.interview_service import (
    generate_interview_questions,
    mark_interview_failed_on_leave,
    score_interview_answers,
)

router = APIRouter()


@router.post("/{interview_id}/generate-questions", response_model=GenerateQuestionsResponse)
async def generate_questions(
    interview_id: str,
    body: GenerateQuestionsRequest,
) -> GenerateQuestionsResponse:
    try:
        return await generate_interview_questions(
            interview_id=interview_id,
            return_questions=body.return_questions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{interview_id}/score-answers", response_model=ScoreAnswersResponse)
async def score_answers(
    interview_id: str,
    body: ScoreAnswersRequest,
) -> ScoreAnswersResponse:
    try:
        return await score_interview_answers(
            interview_id=interview_id,
            fetch_from_db=body.fetch_from_db,
            answers=body.answers,
            test_mode=body.test_mode,
            event_type=body.event_type,
            interview_type=body.interview_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{interview_id}/voice-interview", response_model=CreateRoomResponse)
async def start_voice_interview(interview_id: str) -> CreateRoomResponse:
    try:
        return await conduct_voice_interview(interview_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{interview_id}/report-leave")
async def report_leave(interview_id: str) -> dict:
    """
    Called by the frontend when the candidate leaves mid-interview (tab switch, refresh, logout).
    When fail-cases are enabled: marks the interview Failed with score 0 and signals the SSE done-event.
    When disabled (test mode): silently ignored.
    """
    if not settings.ENABLE_FAIL_CASES:
        return {"status": "ignored", "reason": "fail_cases_disabled"}
    try:
        mark_interview_failed_on_leave(interview_id)
        signal_interview_done(interview_id)
        return {"status": "marked_failed"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{interview_id}/status-stream")
async def interview_status_stream(interview_id: str) -> StreamingResponse:
    async def generate():
        done = await wait_for_interview_done(interview_id, timeout=600.0)
        event_name = "done" if done else "timeout"
        yield f"event: {event_name}\ndata: {{}}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
