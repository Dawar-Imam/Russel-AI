import asyncio
import json
import logging
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    get_schedule_context,
    mark_interview_terminated,
    merge_test_mode_answers,
    save_voice_answers_bulk,
    set_interview_livekit_room,
)
from app.services.interview_validator import TERMINAL_ROUND_STATUSES
from app.services.scheduling_service import compute_token_ttl_seconds

_logger = logging.getLogger("russel.voice_agent")

# ---------------------------------------------------------------------------
# TEMPORARY debugging aid — see task "Debug and validate the Celery task
# responsible for automatically joining the LiveKit agent at the scheduled
# interview time". Safe to delete _DEBUG_DUMP_PATH/_debug_dump_step and their
# call sites in start_scheduled_interview once debugging is done; nothing else
# depends on them.
# ---------------------------------------------------------------------------

_DEBUG_DUMP_PATH = Path(__file__).resolve().parents[3] / "_scheduled_interview_debug.json"


def _debug_dump_step(interview_id: str, step: str, **extra) -> None:
    """Best-effort append of a step record to a JSON file on disk, so
    start_scheduled_interview's progress can be inspected after the fact — it runs
    inside a separate Celery worker process whose console isn't always visible from
    wherever you're debugging. A disk write failure here must never break the actual
    interview flow."""
    try:
        data: dict = {}
        if _DEBUG_DUMP_PATH.exists():
            data = json.loads(_DEBUG_DUMP_PATH.read_text())
        data.setdefault(interview_id, []).append({
            "step": step,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **extra,
        })
        _DEBUG_DUMP_PATH.write_text(json.dumps(data, indent=2, default=str))
    except Exception:
        _logger.debug("start_scheduled_interview: failed to write debug dump", exc_info=True)

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
    job_post_data: str = "",
    candidate_cv_text: str = "",
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

    prompt = build_extract_answers_prompt(history_block, job_post_data, candidate_cv_text)

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
            extracted = await _extract_answers_with_llm(conversation_history, job_post_text, candidate_cv_text)
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


# ---------------------------------------------------------------------------
# Scheduled interviews — agent pre-joins the room at the recruiter-picked time and
# waits for the candidate, instead of everything being created on the candidate's
# click (conduct_voice_interview above, still used as-is for any round that was never
# scheduled — full backward compatibility, nothing above this comment changed).
# ---------------------------------------------------------------------------

def _scheduled_token_ttl(ctx: dict | None) -> timedelta | None:
    """None means "use the LiveKit SDK's default TTL" (on-demand interviews, or a
    scheduled round whose expiry hasn't been computed yet — see
    interview_service.set_interview_livekit_expiry, set once the Calendar webhook
    confirms the schedule)."""
    if not ctx or not ctx.get("livekit_token_expires_at") or not ctx.get("scheduled_timezone"):
        return None
    ttl_seconds = compute_token_ttl_seconds(ctx["livekit_token_expires_at"], ctx["scheduled_timezone"])
    return timedelta(seconds=ttl_seconds)


async def _wait_for_candidate_join(room: rtc.Room, timeout_seconds: float) -> bool:
    """True once a remote participant (the candidate) has joined `room`, or False if
    `timeout_seconds` elapses first. Event-driven (ParticipantConnected), not polling —
    resolves instantly on join instead of waiting for the next poll tick."""
    if room.remote_participants:
        return True

    joined = asyncio.Event()

    def _on_connected(*_args) -> None:
        joined.set()

    room.on("participant_connected")(_on_connected)
    try:
        await asyncio.wait_for(joined.wait(), timeout=timeout_seconds)
        return True
    except asyncio.TimeoutError:
        return False


async def start_scheduled_interview(
    interview_id: str, test_mode: bool = False, join_window_minutes: float | None = None,
) -> None:
    """Celery task entry point (see app/tasks/interview_scheduling_tasks.py), fired via
    an ETA task at the interview's scheduled local time. The agent joins the room ahead
    of the candidate and waits up to settings.SCHEDULED_INTERVIEW_JOIN_WINDOW_MINUTES —
    if the candidate never joins, the round is marked a no-show instead of running the
    interview. Runs to completion inside the Celery worker (blocks for the wait window
    plus, if the candidate does join, the full interview duration) rather than firing a
    background asyncio task the way the on-demand path does, since there is no HTTP
    request/response here to return early from.

    `join_window_minutes` overrides settings.SCHEDULED_INTERVIEW_JOIN_WINDOW_MINUTES —
    None (the only value real ETA dispatch ever passes) keeps existing behavior
    unchanged; only a debugging/test caller has a reason to shrink the wait."""
    _logger.info("start_scheduled_interview: task received for interview=%s", interview_id)
    _debug_dump_step(interview_id, "task_received")

    try:
        schedule_ctx = get_schedule_context(interview_id)
        if schedule_ctx is None:
            _logger.warning("start_scheduled_interview: interview=%s not found (deleted?), aborting", interview_id)
            _debug_dump_step(interview_id, "aborted", reason="interview_not_found")
            return
        _logger.info(
            "start_scheduled_interview: interview fetched from DB -> status=%s scheduled_at=%s timezone=%s round=%s",
            schedule_ctx["status"], schedule_ctx["scheduled_at"], schedule_ctx["scheduled_timezone"], schedule_ctx["round_type_name"],
        )
        _debug_dump_step(
            interview_id, "interview_fetched",
            status=schedule_ctx["status"], scheduled_at=schedule_ctx["scheduled_at"],
            scheduled_timezone=schedule_ctx["scheduled_timezone"], round_type_name=schedule_ctx["round_type_name"],
        )

        # Status validation — between dispatch and this ETA firing, the round could
        # have completed/failed some other way (e.g. an on-demand run), or been
        # unscheduled (delete_interview_round revokes the Celery task, but a revoke
        # racing right against the ETA firing isn't guaranteed to win). Never barge
        # into a room for a round that isn't actually waiting to be run.
        if schedule_ctx["status"].lower() in TERMINAL_ROUND_STATUSES or schedule_ctx["status"] == "In Progress":
            _logger.info(
                "start_scheduled_interview: interview=%s status=%s is not runnable, skipping",
                interview_id, schedule_ctx["status"],
            )
            _debug_dump_step(interview_id, "skipped_status_validation", status=schedule_ctx["status"])
            return
        if schedule_ctx["scheduled_at"] is None:
            _logger.info("start_scheduled_interview: interview=%s has no scheduled_at, skipping", interview_id)
            _debug_dump_step(interview_id, "skipped_status_validation", reason="scheduled_at_is_null")
            return
        _logger.info("start_scheduled_interview: status validation passed for interview=%s", interview_id)
        _debug_dump_step(interview_id, "status_validation_passed")

        job_post_text = ""
        candidate_cv_text = ""
        try:
            ctx = get_interview_context(interview_id)
            _logger.info("start_scheduled_interview: calling fetch_job_post_data/fetch_candidate_cv_relevance for interview=%s", interview_id)
            job_post_text = await fetch_job_post_data(ctx["job_posting_id"], ctx["job_role_id"])
            candidate_cv_text = await fetch_candidate_cv_relevance(ctx["application_id"])
            _logger.info(
                "start_scheduled_interview: external context fetched (job_post_chars=%d, cv_chars=%d) for interview=%s",
                len(job_post_text), len(candidate_cv_text), interview_id,
            )
            _debug_dump_step(interview_id, "external_context_fetched", job_post_chars=len(job_post_text), cv_chars=len(candidate_cv_text))
        except Exception:
            _logger.warning("Could not fetch candidate CV for scheduled interview %s — continuing without it", interview_id)
            _debug_dump_step(interview_id, "external_context_fetch_failed")

        _logger.info("start_scheduled_interview: creating LiveKit room for interview=%s", interview_id)
        room_response = await create_room()
        set_interview_livekit_room(interview_id, room_response.room_name)
        _logger.info("start_scheduled_interview: room=%s created for interview=%s", room_response.room_name, interview_id)
        _debug_dump_step(interview_id, "room_created", room_name=room_response.room_name)

        ttl = _scheduled_token_ttl(get_schedule_context(interview_id))
        _logger.info("start_scheduled_interview: agent token ttl=%s for interview=%s", ttl, interview_id)
        _debug_dump_step(interview_id, "token_ttl_computed", ttl_seconds=ttl.total_seconds() if ttl else None)
        agent_token_builder = (
            AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity("russel-agent")
            .with_name("Russel AI")
            .with_grants(
                VideoGrants(room_join=True, room=room_response.room_name, can_publish=True, can_subscribe=True)
            )
        )
        agent_token = agent_token_builder.with_ttl(ttl) if ttl else agent_token_builder
        _logger.info("start_scheduled_interview: agent token generated for interview=%s, connecting to LiveKit", interview_id)
        _debug_dump_step(interview_id, "agent_token_generated")

        agent_room = rtc.Room()
        await agent_room.connect(settings.LIVEKIT_URL, agent_token.to_jwt())
        effective_window_minutes = join_window_minutes if join_window_minutes is not None else settings.SCHEDULED_INTERVIEW_JOIN_WINDOW_MINUTES
        _logger.info(
            "start_scheduled_interview: agent joined room=%s for interview=%s, waiting up to %s min for candidate",
            room_response.room_name, interview_id, effective_window_minutes,
        )
        _debug_dump_step(interview_id, "agent_joined_room", room_name=room_response.room_name, join_window_minutes=effective_window_minutes)

        window_seconds = effective_window_minutes * 60
        candidate_joined = await _wait_for_candidate_join(agent_room, window_seconds)
        _logger.info("start_scheduled_interview: candidate_joined=%s for interview=%s", candidate_joined, interview_id)
        _debug_dump_step(interview_id, "wait_for_candidate_join_done", candidate_joined=candidate_joined)
    except Exception:
        _logger.exception("start_scheduled_interview: FAILED for interview=%s", interview_id)
        _debug_dump_step(interview_id, "exception", traceback=traceback.format_exc())
        raise

    if not candidate_joined:
        _logger.info("Scheduled interview %s: candidate never joined, marking no-show", interview_id)
        mark_interview_terminated(
            interview_id,
            f"Candidate did not join within {effective_window_minutes} minutes "
            "of the scheduled time — marked as no-show.",
        )
        _debug_dump_step(interview_id, "marked_no_show")
        try:
            await agent_room.disconnect()
        except Exception:
            pass
        await _force_room_teardown(room_response.room_name)
        return

    # Candidate joined — run the interview exactly like the on-demand path does, just
    # awaited directly instead of fire-and-forget (this task already owns its own
    # lifetime for the whole interview duration).
    await _run_and_store(agent_room, interview_id, job_post_text, test_mode=test_mode, candidate_cv_text=candidate_cv_text)


async def join_scheduled_room(interview_id: str, test_mode: bool = False) -> CreateRoomResponse:
    """Candidate-facing entry point for /interviews/{id}/join. If the agent has already
    pre-joined a room for this scheduled interview (Interviews.livekit_room_name set by
    start_scheduled_interview above), mint the candidate a token for that existing room.
    Otherwise — a round that was never scheduled, or scheduling isn't configured for
    this job — falls back to the original on-demand behavior unchanged."""
    ctx = get_schedule_context(interview_id)
    room_name = ctx["livekit_room_name"] if ctx else None

    if not room_name:
        return await conduct_voice_interview(interview_id, test_mode=test_mode)

    identity = f"candidate-{uuid.uuid4().hex[:8]}"
    ttl = _scheduled_token_ttl(ctx)
    token_builder = (
        AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True))
    )
    token = token_builder.with_ttl(ttl) if ttl else token_builder
    return CreateRoomResponse(url=settings.LIVEKIT_URL, token=token.to_jwt(), room_name=room_name, identity=identity)
