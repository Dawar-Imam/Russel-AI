import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai.voice_agent.interview_state import store_conclude_result
from app.ai.voice_agent.room_connection import (
    CreateRoomResponse,
    conduct_voice_interview,
    join_scheduled_room,
    pop_processing_failure,
    signal_interview_done,
    wait_for_interview_done,
)
from app.core.config import settings
from app.schemas.interviews import (
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    SaveAnswerRequest,
    ScoreAnswersRequest,
    ScoreAnswersResponse,
)
from app.services.interview_service import (
    InterviewAlreadyCompletedError,
    InterviewDeletedPostFailError,
    clear_test_mode_cache,
    generate_interview_questions,
    mark_interview_failed_on_leave,
    save_candidate_answer,
    score_interview_answers,
)


class ConcludeInterviewRequest(BaseModel):
    passed: bool
    reason: str

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
            test_mode=body.test_mode,
        )
    except InterviewDeletedPostFailError as exc:
        # Distinct from the generic 404 below — the frontend must redirect straight to
        # application-progress on this one, not show an error/retry state (it can't be
        # confused with "questions not yet generated", which never reaches this branch;
        # see InterviewDeletedPostFailError's docstring). application_id is included
        # because the frontend only has interview_id in scope (route param) and the
        # redirect target (/application-progress/:applicationId) needs it.
        raise HTTPException(
            status_code=410,
            detail={"code": "interview_deleted_post_fail", "application_id": exc.application_id},
        ) from exc
    except InterviewAlreadyCompletedError as exc:
        # Carries application_id — see the exception's docstring — so the frontend's
        # "already completed" screen can point its Back button at
        # /application-progress/:applicationId instead of falling back to browser history
        # (which can land on an unrelated page, e.g. /auth, depending on how the tab got here).
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "application_id": exc.application_id},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{interview_id}/save-answer")
async def save_answer(interview_id: str, body: SaveAnswerRequest) -> dict:
    """
    Called by the frontend on every answer change (debounced for free-text, immediate
    for MCQ picks) while a written round is in progress, so a refresh/crash/network
    drop never loses progress. No-ops silently if the round is already terminal.
    """
    try:
        save_candidate_answer(interview_id, body.iq_id, body.candidate_answer)
        return {"status": "ok"}
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
            event_type=body.event_type,
            interview_type=body.interview_type,
            test_mode=body.test_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{interview_id}/voice-interview", response_model=CreateRoomResponse)
async def start_voice_interview(interview_id: str, test_mode: bool = False) -> CreateRoomResponse:
    try:
        return await conduct_voice_interview(interview_id, test_mode=test_mode)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{interview_id}/join", response_model=CreateRoomResponse)
async def join_interview(interview_id: str, test_mode: bool = False) -> CreateRoomResponse:
    """Candidate entry point for a (possibly scheduled) interview — replaces the old
    always-create-everything /voice-interview call for the Application Progress page's
    "Enter Interview Room" action. If the AI agent already pre-joined this interview's
    room (a scheduled round whose time has arrived), mints a token for that same room;
    otherwise falls back to the original on-demand flow unchanged."""
    try:
        return await join_scheduled_room(interview_id, test_mode=test_mode)
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


@router.post("/{interview_id}/clear-test-cache")
async def clear_test_cache(interview_id: str) -> dict:
    """
    Called by the frontend when leaving the interview room page in test mode.
    Flushes the in-memory test-mode question/answer cache for this interview_id
    so it never resurfaces (stale questions/scores) on a later test run.
    No-op / harmless if there was nothing cached (e.g. real-mode interviews).
    """
    clear_test_mode_cache(interview_id)
    return {"status": "cleared", "interview_id": interview_id}


@router.post("/{interview_id}/conclude")
async def conclude_interview(interview_id: str, body: ConcludeInterviewRequest) -> dict:
    """
    Called by the voice agent's conclude_interview tool (or directly in tests).
    Stores the pass/fail result so _run_and_store can act on it after the agent disconnects.
    """
    try:
        store_conclude_result(interview_id, body.passed, body.reason)
        return {"status": "ok", "interview_id": interview_id, "passed": body.passed}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{interview_id}/status-stream")
async def interview_status_stream(interview_id: str) -> StreamingResponse:
    async def generate():
        timeout = 3600 if settings.DEBUG_MODE else (settings.INTERVIEW_DURATION_MINUTES + 1) * 60
        done = await wait_for_interview_done(interview_id, timeout=timeout)
        if not done:
            yield "event: timeout\ndata: {}\n\n"
            return

        failure_reason = pop_processing_failure(interview_id)
        if failure_reason:
            yield f"event: failed\ndata: {json.dumps({'reason': failure_reason})}\n\n"
        else:
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
