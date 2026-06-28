import asyncio
import json
import logging
import uuid

from langchain_core.messages import HumanMessage
from livekit import rtc
from livekit.api import AccessToken, CreateRoomRequest, LiveKitAPI, VideoGrants
from pydantic import BaseModel

from app.ai.voice_agent.agent import run_voice_agent
from app.core.config import get_llm, settings
from app.services.interview_service import (
    get_interview_questions,
    mark_interview_failed_on_leave,
    mark_interview_terminated,
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

async def _extract_answers_with_llm(questions: list, conversation_history: list[dict]) -> list[str]:
    """Map conversation history onto the ordered question list and return one answer per question."""
    questions_block = "\n".join(f"{i + 1}. {q.question_text}" for i, q in enumerate(questions))
    history_block = "\n".join(
        f"{'Interviewer' if t['role'] == 'assistant' else 'Candidate'}: {t['text']}"
        for t in conversation_history
    )

    prompt = (
        "You are processing a recorded voice interview transcript.\n\n"
        "These are the intended interview questions (in order):\n"
        f"{questions_block}\n\n"
        "This is the full conversation between the interviewer and the candidate:\n"
        f"{history_block}\n\n"
        "Your task: extract the candidate's final answer for each question.\n"
        "Return a JSON array of strings — one entry per question, in the same order.\n\n"
        "STRICT RULES — read carefully:\n"
        "1. A question was answered ONLY if the candidate's voice turns in the transcript "
        "contain a substantive response to that specific question.\n"
        "2. If the interviewer asked a question but the candidate never responded to it "
        "(the interview ended, the candidate was silent, or the session was cut short before "
        "they replied), use an empty string \"\" for that position.\n"
        "3. Do NOT infer, fabricate, or carry over answers from adjacent questions. "
        "If there is no clear candidate response mapped to the question, it is unanswered.\n"
        "4. The interviewer may have asked follow-up or counter-questions — "
        "consolidate all candidate turns related to a single base question into one answer string.\n"
        "5. If the candidate gave a partial reply and then the interview ended mid-answer, "
        "include only what was actually said — do not complete or extend it.\n\n"
        "Return ONLY the JSON array, no explanation.\n\n"
        'Example: ["full answer to Q1", "", "partial answer to Q3", ""]'
    )

    llm = get_llm(temperature=0)
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    raw = response.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _run_and_store(agent_room: rtc.Room, interview_id: str, questions: list) -> None:
    """Fire-and-forget task: run voice session, post-process, bulk-save."""
    done_event = _get_done_event(interview_id)
    try:
        conversation_history, terminated_reason = await run_voice_agent(
            agent_room, questions, enable_fail_cases=settings.ENABLE_FAIL_CASES
        )
        await agent_room.disconnect()

        # Cheating or policy termination — mark failed, do not score
        if terminated_reason:
            _logger.warning(
                "Interview %s terminated early: %s", interview_id, terminated_reason
            )
            mark_interview_terminated(interview_id, terminated_reason)
            done_event.set()
            return

        if not conversation_history:
            _logger.warning("Empty conversation history for interview %s — SSE will timeout", interview_id)
            return

        _logger.info(
            "Post-processing %d conversation turns for interview %s",
            len(conversation_history),
            interview_id,
        )

        answers = await _extract_answers_with_llm(questions, conversation_history)

        pairs = [
            (questions[i].iq_id, answers[i])
            for i in range(min(len(questions), len(answers)))
            if answers[i]
        ]

        if not pairs:
            _logger.warning("No answers extracted for interview %s — SSE will timeout", interview_id)
            return

        save_voice_answers_bulk(interview_id, pairs)
        _logger.info("Stored %d answers for interview %s", len(pairs), interview_id)
        done_event.set()

    except Exception:
        _logger.exception("Voice agent task failed for interview %s", interview_id)
        # done_event deliberately NOT set — SSE times out, preventing scoring of empty answers


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def conduct_voice_interview(interview_id: str) -> CreateRoomResponse:
    questions = get_interview_questions(interview_id)
    if not questions:
        raise ValueError(f"No questions found for interview {interview_id}")

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

    asyncio.create_task(_run_and_store(agent_room, interview_id, questions))

    return room_response
