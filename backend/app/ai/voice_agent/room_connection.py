import asyncio
import json
import logging
import uuid

from langchain_core.messages import HumanMessage
from livekit import rtc
from livekit.api import AccessToken, CreateRoomRequest, DeleteRoomRequest, LiveKitAPI, VideoGrants
from pydantic import BaseModel

from app.ai.ai_services.cv_relevance_service import fetch_candidate_cv_relevance
from app.ai.ai_services.job_post_service import fetch_job_post_data
from app.ai.voice_agent.agent import run_voice_agent
from app.ai.voice_agent.interview_state import pop_conclude_result
from app.ai.voice_agent.prompts import build_extract_answers_prompt
from app.core.config import get_llm, settings
from app.services.interview_service import (
    get_interview_context,
    mark_interview_terminated,
    merge_test_mode_answers,
    save_voice_answers_bulk,
)

_logger = logging.getLogger("russel.voice_agent")

# ---------------------------------------------------------------------------
# Done-event store (used by SSE endpoint to wait for processing completion)
# ---------------------------------------------------------------------------

_interview_done: dict[str, asyncio.Event] = {}


def _get_done_event(interview_id: str) -> asyncio.Event:
    if interview_id not in _interview_done:
        _interview_done[interview_id] = asyncio.Event()
    return _interview_done[interview_id]


def signal_interview_done(interview_id: str) -> None:
    """Immediately set the done-event so the SSE endpoint resolves (used after force-termination)."""
    _get_done_event(interview_id).set()


async def wait_for_interview_done(interview_id: str, timeout: float = 600.0) -> bool:
    """Wait until answers are stored for this interview. Returns True on done, False on timeout."""
    event = _get_done_event(interview_id)
    try:
        await asyncio.wait_for(asyncio.shield(event.wait()), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False
    finally:
        _interview_done.pop(interview_id, None)


# ---------------------------------------------------------------------------
# Processing-failure store — lets the SSE endpoint tell a post-processing
# crash (extraction raised / returned nothing) apart from a normal completion,
# so the frontend can show a specific error instead of waiting out the full
# SSE timeout.
# ---------------------------------------------------------------------------

_processing_failures: dict[str, str] = {}


def pop_processing_failure(interview_id: str) -> str | None:
    """Consume and return the recorded post-processing failure reason, or None."""
    return _processing_failures.pop(interview_id, None)


def _fail_processing(interview_id: str, reason: str, test_mode: bool) -> None:
    """Fast-fail path for post-processing errors — marks the interview terminated
    and resolves the SSE wait immediately instead of leaving done_event unset,
    which previously left the frontend waiting out the full interview-duration
    SSE timeout before showing any error."""
    _logger.warning("Interview %s processing failed: %s", interview_id, reason)
    if not test_mode:
        mark_interview_terminated(interview_id, reason)
    _processing_failures[interview_id] = reason
    _get_done_event(interview_id).set()


# ---------------------------------------------------------------------------
# Room creation
# ---------------------------------------------------------------------------

class CreateRoomResponse(BaseModel):
    url: str
    token: str
    room_name: str
    identity: str


async def create_room() -> CreateRoomResponse:
    room_name = f"interview-room-{uuid.uuid4().hex[:8]}"
    identity = f"candidate-{uuid.uuid4().hex[:8]}"

    lkapi = LiveKitAPI(settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    await lkapi.room.create_room(CreateRoomRequest(name=room_name))
    await lkapi.aclose()

    token = (
        AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True))
    )

    return CreateRoomResponse(
        url=settings.LIVEKIT_URL,
        token=token.to_jwt(),
        room_name=room_name,
        identity=identity,
    )


# ---------------------------------------------------------------------------
# LLM post-processing
# ---------------------------------------------------------------------------

async def _extract_answers_with_llm(
    conversation_history: list[dict],
) -> list[dict]:
    """
    Extract question-answer pairs from the interview transcript.

    Returns a list of dicts:
        question : str
        answer   : str — only non-empty answers are returned
    """
    history_block = "\n".join(
        f"{'Interviewer' if t['role'] == 'assistant' else 'Candidate'}: {t['text']}"
        for t in conversation_history
    )

    prompt = build_extract_answers_prompt(history_block)

    llm = get_llm(temperature=0)
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    raw = response.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    data = json.loads(raw)

    if not isinstance(data, list):
        raise ValueError(f"LLM returned non-list type: {type(data).__name__}")

    result: list[dict] = []

    for item in data:
        if not isinstance(item, dict):
            _logger.warning("Skipping non-dict item in LLM output: %r", item)
            continue
        answer = item.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            continue  # omit unanswered / malformed entries
        result.append({
            "question": str(item.get("question") or ""),
            "answer": answer.strip(),
        })

    return result


# ---------------------------------------------------------------------------
# Guaranteed room teardown fallback
# ---------------------------------------------------------------------------

async def _force_room_teardown(room_name: str) -> None:
    """Guarantee the candidate's client gets disconnected once the agent session
    ends, even if the `interview_ended` data message (agent.py conclude_interview)
    was dropped or the agent process died right after storing the conclude result.

    Deletes the LiveKit room outright — per LiveKit's RoomService docs this
    disconnects every remaining participant, so it doesn't require knowing the
    candidate's participant identity (unlike remove_participant)."""
    if not room_name:
        return
    try:
        lkapi = LiveKitAPI(settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        try:
            await lkapi.room.delete_room(DeleteRoomRequest(room=room_name))
        finally:
            await lkapi.aclose()
    except Exception as exc:
        _logger.warning("Failed to force-delete room %s: %s", room_name, exc)


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _run_and_store(
    agent_room: rtc.Room,
    interview_id: str,
    job_post_text: str,
    test_mode: bool = False,
    candidate_cv_text: str = "",
) -> None:
    """Fire-and-forget task: run voice session, post-process, bulk-save."""
    done_event = _get_done_event(interview_id)
    try:
        conversation_history, terminated_reason = await run_voice_agent(
            agent_room,
            job_post_text,
            interview_id,
            no_response_timeout_seconds=settings.NO_RESPONSE_TIMEOUT_SECONDS,
            cancel_interview_on_no_response=settings.CANCEL_INTERVIEW_ON_NO_RESPONSE,
            candidate_cv_text=candidate_cv_text,
        )
        try:
            # The conclude_interview tool may have already disconnected this room
            # itself — a redundant disconnect call here shouldn't ever abort the
            # rest of post-processing (extraction, save, status update).
            await agent_room.disconnect()
        except Exception as exc:
            _logger.debug("agent_room.disconnect() no-op/failed (already disconnected?): %s", exc)
        # Fallback: guarantee the candidate is disconnected even if the
        # `interview_ended` data message never reached them.
        await _force_room_teardown(agent_room.name)

        # =============== conversation history extraction (always runs) ===============
        # Regardless of how the interview ended (cheating, candidate left, agent
        # cancelled, no-response timeout, natural completion) — if there's a
        # transcript, extract and store it. The pass/fail/terminated outcome below
        # only affects Interviews.feedback/status, not whether answers get saved.
        if not conversation_history:
            _fail_processing(
                interview_id,
                "No conversation was recorded during the interview.",
                test_mode,
            )
            return

        _logger.info(
            "Post-processing %d conversation turns for interview %s",
            len(conversation_history),
            interview_id,
        )

        try:
            extracted = await _extract_answers_with_llm(conversation_history)
        except Exception:
            _logger.exception("Answer extraction failed for interview %s", interview_id)
            _fail_processing(
                interview_id,
                "Failed to process your interview answers. Please contact support.",
                test_mode,
            )
            return

        if not extracted:
            _fail_processing(
                interview_id,
                "No answers could be extracted from the interview.",
                test_mode,
            )
            return

        if test_mode:
            # Merge into the in-memory cache instead of writing to the DB.
            merge_test_mode_answers(interview_id, extracted)
        else:
            save_voice_answers_bulk(interview_id, extracted)
        _logger.info("Stored %d answers for interview %s", len(extracted), interview_id)

        # =============== check if interview passed (feedback only) ===============
        # Python-side no-response termination — candidate didn't respond, probably
        # due to network failure.
        if terminated_reason:
            _logger.warning(
                "Interview %s terminated early: %s", interview_id, terminated_reason
            )
            if not test_mode:
                mark_interview_terminated(interview_id, terminated_reason)
            done_event.set()
            return

        # LLM-decided outcome via conclude_interview tool
        conclude = pop_conclude_result(interview_id)
        if conclude is None:
            _logger.warning("No conclude result for interview %s — assuming pass", interview_id)
            conclude = {"passed": True, "reason": "natural_completion"}

        if not conclude["passed"]:
            _logger.warning(
                "Interview %s concluded as FAIL: %s", interview_id, conclude["reason"]
            )
            if not test_mode:
                mark_interview_terminated(interview_id, conclude["reason"])
            done_event.set()
            return

        _logger.info("Interview %s concluded as PASS", interview_id)
        done_event.set()

    except Exception:
        _logger.exception("Voice agent task failed for interview %s", interview_id)
        # done_event deliberately NOT set — SSE times out, preventing scoring of empty answers


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def conduct_voice_interview(interview_id: str, test_mode: bool = False) -> CreateRoomResponse:
    # questions = get_interview_questions(interview_id, test_mode=test_mode)
    # if not questions:
    #     raise ValueError(f"No questions found for interview {interview_id}")

    job_post_text = ""
    candidate_cv_text = ""
    try:
        ctx = get_interview_context(interview_id)
        application_id = ctx["application_id"]
        job_posting_id = ctx["job_posting_id"]
        job_role_id = ctx["job_role_id"]

        job_post_text = await fetch_job_post_data(job_posting_id, job_role_id)
        candidate_cv_text = await fetch_candidate_cv_relevance(application_id)

    except Exception:
        _logger.warning("Could not fetch candidate CV for interview %s — continuing without it", interview_id)

    room_response = await create_room()

    agent_token = (
        AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity("russel-agent")
        .with_name("Russel AI")
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_response.room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
    )

    agent_room = rtc.Room()
    await agent_room.connect(settings.LIVEKIT_URL, agent_token.to_jwt())

    asyncio.create_task(
        _run_and_store(
            agent_room, interview_id, job_post_text,
            test_mode=test_mode, candidate_cv_text=candidate_cv_text,
        )
    )

    return room_response
