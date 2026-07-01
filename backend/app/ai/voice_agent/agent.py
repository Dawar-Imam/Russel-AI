import asyncio
import contextlib
import json
import logging
import re
import time
from collections.abc import AsyncGenerator

from livekit import rtc
from livekit.agents import Agent, AgentSession, llm, stt as agents_stt
from livekit.agents.utils import http_context
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import deepgram, elevenlabs, openai, silero

from app.ai.voice_agent.prompts import (
    PRESENCE_CHECK_INSTRUCTIONS,
    WELCOME_INSTRUCTIONS,
    build_system_prompt,
)
from app.ai.voice_agent.whisper_stt import OpenRouterWhisperSTT

from app.core.config import settings
from app.schemas.interviews import QuestionItem

_logger = logging.getLogger("russel.voice_agent")

_CHEAT_PHRASES = [
    "using chatgpt",
    "using gpt",
    "using claude",
    "using ai to",
    "i am cheating",
    "i'm cheating",
    "im cheating",
    "reading answers",
    "reading from notes",
    "copy pasting",
    "copied from",
    "someone is helping me",
    "someone helping me",
    "i am using ai",
    "i'm using ai",
    "im using ai",
]

TERMINATION_REASON_CHEATING = "Candidate admitted to cheating during the voice interview. Interview terminated."
TERMINATION_REASON_AGENT_CANCELLED = (
    "Interview cancelled by the AI interviewer due to insufficient correct answers "
    "or repeated misconduct."
)

_CANCEL_TOKEN = "/cancel-interview"
_PASS_TOKEN = "/pass-interview"
_CONTROL_TOKEN_RE = re.compile(r"/cancel-interview|/pass-interview", re.IGNORECASE)


def _compute_remaining(start_time: float, duration_seconds: float) -> int:
    """Return remaining interview seconds (floored at 0)."""
    return round(max(0.0, duration_seconds - (time.time() - start_time)))


class InterviewerAgent(Agent):
    def __init__(
        self,
        questions: list[QuestionItem],
        room: rtc.Room,
        duration_minutes: int = settings.INTERVIEW_DURATION_MINUTES,
        candidate_cv_text: str = "",
    ) -> None:
        self._duration_seconds = duration_minutes * 60
        self._start_time: float | None = None
        self._interrupted = asyncio.Event()

        questions_block = "\n".join(f"{i + 1}. {q.question_text}" for i, q in enumerate(questions))
        super().__init__(
            instructions=build_system_prompt(
                questions_block, duration_minutes, len(questions), candidate_cv_text
            )
        )
        self._room = room

    async def on_enter(self) -> None:
        self._start_time = time.time()
        await self.session.generate_reply(instructions=WELCOME_INSTRUCTIONS)

    def _get_remaining_seconds(self) -> float:
        if self._start_time is None:
            return float(self._duration_seconds)
        return max(0.0, self._duration_seconds - (time.time() - self._start_time))

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list,
        model_settings=None,
    ) -> AsyncGenerator:
        """Inject remaining-time into context. Text is forwarded to the frontend
        from tts_node (in sync with speech), not here — the LLM generates far
        faster than the candidate hears it, so publishing at this stage desyncs
        the chat bubble from the voice."""
        remaining_secs = round(self._get_remaining_seconds())
        if remaining_secs < 60:
            time_note = (
                f"Remaining interview time: {remaining_secs} seconds. "
                "Time is up. Do NOT ask any more questions. In this reply, first say one short "
                "line that time is up, then immediately deliver the interview closing statement."
            )
        else:
            time_note = f"Remaining interview time: {remaining_secs} seconds."
        chat_ctx.add_message(role="system", content=time_note)

        async with self.session.llm.chat(
            chat_ctx=chat_ctx,
            tools=tools,
        ) as stream:
            async for chunk in stream:
                yield chunk

    async def tts_node(self, text, model_settings=None) -> AsyncGenerator:
        """Forward each text segment to the frontend right as it's handed to TTS
        for synthesis — this tracks what's about to be spoken, not what the LLM
        already generated, so the chat bubble fills in step with the voice.
        Stops forwarding immediately once the candidate interrupts."""
        self._interrupted.clear()

        async def _gated_text():
            async for segment in text:
                if self._interrupted.is_set():
                    break
                asyncio.ensure_future(self._publish_chunk(segment))
                yield segment

        async for frame in Agent.default.tts_node(self, _gated_text(), model_settings):
            yield frame

    def mark_interrupted(self) -> None:
        self._interrupted.set()

    async def _publish_chunk(self, text: str) -> None:
        try:
            await self._room.local_participant.publish_data(
                json.dumps({"role": "assistant_chunk", "text": text}).encode(),
                reliable=True,
            )
        except Exception as exc:
            _logger.debug("Chunk publish failed: %s", exc)


# ---------------------------------------------------------------------------
# No-response timeout checker — extracted for testability
# ---------------------------------------------------------------------------

NO_RESPONSE_GRACE_SECONDS = 60
"""Don't fire the 'are you still there?' presence check during the opening
minute of an interview — the candidate is still settling in/listening to the
intro and first question, not necessarily unresponsive."""


async def _no_response_checker(
    *,
    disconnected: asyncio.Event,
    last_response_time: list[float],
    no_response_count: list[int],
    connection_quality_poor: list[bool],
    cancel_on_no_response: int,
    timeout_seconds: int,
    get_session,
    publish_fn,
    terminated_reason: list[str | None],
    session_start_time: float = 0.0,
    grace_period_seconds: int = 0,
) -> None:
    """
    Polls every second. When the candidate has been silent for `timeout_seconds`
    (and at least `grace_period_seconds` have passed since the interview started):
    - Triggers the LLM to ask if the candidate is still present.
    - If cancel_on_no_response > 0 and connection quality is good: decrements counter.
      When counter hits 0 the interview is cancelled.
    """
    while not disconnected.is_set():
        await asyncio.sleep(1.0)
        if disconnected.is_set():
            break

        if time.time() - session_start_time < grace_period_seconds:
            continue

        elapsed = time.time() - last_response_time[0]
        if elapsed < timeout_seconds:
            continue

        # Trigger presence confirmation
        session = get_session()
        if session is not None:
            asyncio.ensure_future(
                session.generate_reply(instructions=PRESENCE_CHECK_INSTRUCTIONS)
            )

        # Decrement cancel counter only when connection quality is fine
        if cancel_on_no_response > 0 and not connection_quality_poor[0]:
            no_response_count[0] -= 1
            if no_response_count[0] <= 0:
                reason = "Interview cancelled: no response from candidate."
                terminated_reason[0] = reason
                asyncio.ensure_future(
                    publish_fn({
                        "role": "control",
                        "event": "terminated",
                        "reason": reason,
                    })
                )
                disconnected.set()
                return

        # Reset timer so we don't fire again immediately
        last_response_time[0] = time.time()


# ---------------------------------------------------------------------------
# STT engine selection — Deepgram is primary (native streaming + interim
# results); OpenRouter Whisper is the secondary/fallback engine used only
# when no Deepgram key is configured.
# ---------------------------------------------------------------------------

def _build_stt_engine(vad):
    if settings.DEEPGRAM_API_KEY:
        _logger.info("STT engine: Deepgram nova-3 (primary)")
        return deepgram.STT(model="nova-3", api_key=settings.DEEPGRAM_API_KEY)

    _logger.warning("No Deepgram API key configured — falling back to Whisper STT (secondary)")
    whisper_stt = OpenRouterWhisperSTT(
        api_key=settings.OPENROUTER_API_KEY,
        model=settings.WHISPER_MODEL,
    )
    return agents_stt.StreamAdapter(stt=whisper_stt, vad=vad)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_voice_agent(
    room: rtc.Room,
    questions: list[QuestionItem],
    duration_minutes: int = settings.INTERVIEW_DURATION_MINUTES,
    enable_fail_cases: bool = True,
    no_response_timeout_seconds: int = 30,
    cancel_interview_on_no_response: int = 0,
    candidate_cv_text: str = "",
) -> tuple[list[dict], str | None]:
    """
    Run the voice interview session.
    Returns (conversation_history, terminated_reason).
    terminated_reason is None for normal completion, or a string if terminated early.
    """
    _logger.info("Voice agent starting — %d questions, %d min", len(questions), duration_minutes)

    duration_seconds = duration_minutes * 60
    session_start = time.time()

    def _get_remaining() -> int:
        return _compute_remaining(session_start, duration_seconds)

    conversation_history: list[dict] = []
    terminated_reason: list[str | None] = [None]
    last_user_response_time: list[float] = [time.time()]
    no_response_count: list[int] = [cancel_interview_on_no_response]
    connection_quality_poor: list[bool] = [False]
    session_ref: list = [None]
    interviewer_agent_ref: list = [None]

    async def _publish(payload: dict) -> None:
        try:
            await room.local_participant.publish_data(
                json.dumps(payload).encode(),
                reliable=True,
            )
        except Exception as exc:
            _logger.debug("Transcript publish failed: %s", exc)

    def _on_conversation_item(ev) -> None:
        item = ev.item
        role = getattr(item, "role", None)
        if role != "assistant":
            return
        text = item.text_content
        if not text or not text.strip():
            return
        clean_text = text.strip()

        lowered = clean_text.lower()
        cancel_signal = _CANCEL_TOKEN in lowered
        pass_signal = _PASS_TOKEN in lowered
        if cancel_signal or pass_signal:
            # Strip the control token — it's a backend signal, never shown/spoken.
            clean_text = _CONTROL_TOKEN_RE.sub("", clean_text).strip()
            if not clean_text:
                clean_text = "The interview has ended. Thank you for your time."

        remaining = _get_remaining()
        # conversation_history stores the clean text (used by post-processing LLM)
        msg = {"role": "assistant", "text": clean_text, "remaining_time": remaining}
        conversation_history.append(msg)
        # frontend sees remaining time appended to the message text
        m, s = divmod(remaining, 60)
        display_text = f"{clean_text} [remaining: {m:02d}:{s:02d}]"
        asyncio.ensure_future(_publish({**msg, "text": display_text}))
        _logger.info("Agent said: %s", clean_text)

        if cancel_signal and enable_fail_cases:
            _logger.warning("Agent fired /cancel-interview — marking interview failed")
            terminated_reason[0] = TERMINATION_REASON_AGENT_CANCELLED
            asyncio.ensure_future(
                _publish({
                    "role": "control",
                    "event": "terminated",
                    "reason": TERMINATION_REASON_AGENT_CANCELLED,
                })
            )
            disconnected.set()
        elif pass_signal:
            _logger.info("Agent fired /pass-interview — ending early for scoring")
            disconnected.set()

    def _on_user_transcript(ev) -> None:
        transcript = ev.transcript.strip() if ev.transcript else ""
        if not transcript:
            return

        if not ev.is_final:
            # Interim transcript — stream to frontend only, not authoritative.
            asyncio.ensure_future(_publish({"role": "user_chunk", "text": transcript}))
            return

        last_user_response_time[0] = time.time()  # reset no-response timer
        msg = {"role": "user", "text": transcript, "remaining_time": _get_remaining()}
        conversation_history.append(msg)
        asyncio.ensure_future(_publish(msg))
        _logger.info("User said: %s", transcript)

        if enable_fail_cases:
            lowered = transcript.lower()
            if any(phrase in lowered for phrase in _CHEAT_PHRASES):
                _logger.warning("Cheating detected — terminating: %r", transcript)
                terminated_reason[0] = TERMINATION_REASON_CHEATING
                asyncio.ensure_future(
                    _publish({
                        "role": "control",
                        "event": "terminated",
                        "reason": TERMINATION_REASON_CHEATING,
                    })
                )
                disconnected.set()

    def _on_speech_interrupted(ev) -> None:
        if interviewer_agent_ref[0] is not None:
            interviewer_agent_ref[0].mark_interrupted()
        asyncio.ensure_future(_publish({"role": "control", "event": "interrupted"}))
        _logger.info("Agent speech interrupted by candidate")

    def _on_participant_disconnected(participant: rtc.RemoteParticipant) -> None:
        if participant.identity and not participant.identity.startswith("russel-"):
            _logger.info("Candidate %s disconnected — ending voice session", participant.identity)
            disconnected.set()

    def _on_connection_quality_changed(participant, quality) -> None:
        if isinstance(participant, rtc.RemoteParticipant) and not str(participant.identity).startswith("russel-"):
            quality_name = quality.name.lower() if hasattr(quality, "name") else str(quality).lower()
            connection_quality_poor[0] = quality_name in ("poor", "lost")
            _logger.info(
                "Connection quality for %s: %s (poor=%s)",
                participant.identity,
                quality_name,
                connection_quality_poor[0],
            )

    disconnected = asyncio.Event()
    room.on("disconnected")(lambda *_: disconnected.set())
    room.on("participant_disconnected")(_on_participant_disconnected)
    room.on("connection_quality_changed")(_on_connection_quality_changed)

    async with http_context.open():
        vad = silero.VAD.load()
        session = AgentSession(
            vad=vad,
            stt=_build_stt_engine(vad),
            llm=openai.LLM(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY),
            tts=elevenlabs.TTS(
                model="eleven_turbo_v2_5",
                voice_id=settings.ELEVENLABS_VOICE_ID,
                api_key=settings.ELEVENLABS_API_KEY,
            ),
            turn_handling={
                "endpointing": {"min_delay": 1.8, "max_delay": 4.0},
                "interruption": {
                    "enabled": True,
                    "min_duration": 0.2,
                    "min_words": 1,
                },
                "preemptive_generation": {"enabled": False},
            },
        )
        session_ref[0] = session

        session.on("conversation_item_added")(_on_conversation_item)
        session.on("user_input_transcribed")(_on_user_transcript)
        session.on("agent_speech_interrupted")(_on_speech_interrupted)

        checker_task = asyncio.create_task(
            _no_response_checker(
                disconnected=disconnected,
                last_response_time=last_user_response_time,
                no_response_count=no_response_count,
                connection_quality_poor=connection_quality_poor,
                cancel_on_no_response=cancel_interview_on_no_response,
                timeout_seconds=no_response_timeout_seconds,
                get_session=lambda: session_ref[0],
                publish_fn=_publish,
                terminated_reason=terminated_reason,
                session_start_time=session_start,
                grace_period_seconds=NO_RESPONSE_GRACE_SECONDS,
            )
        )

        interviewer_agent_ref[0] = InterviewerAgent(
            questions, room, duration_minutes, candidate_cv_text=candidate_cv_text
        )
        await session.start(
            agent=interviewer_agent_ref[0],
            room=room,
            room_options=RoomOptions(),
        )

        try:
            await disconnected.wait()
        finally:
            checker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await checker_task

        await session.aclose()

    _logger.info(
        "Voice agent finished — %d turns, terminated_reason=%s",
        len(conversation_history),
        terminated_reason[0],
    )
    return conversation_history, terminated_reason[0]
