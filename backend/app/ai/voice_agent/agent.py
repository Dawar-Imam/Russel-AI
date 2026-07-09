import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncGenerator

from livekit import rtc
from livekit.agents import Agent, AgentSession, function_tool, llm, stt as agents_stt
from livekit.agents.utils import http_context
from livekit.agents.voice.room_io import AudioInputOptions, RoomOptions
from livekit.plugins import deepgram, elevenlabs, noise_cancellation, openai, silero
from livekit.plugins.elevenlabs import VoiceSettings
from app.ai.voice_agent.interview_state import store_conclude_result
from app.ai.voice_agent.prompts import (
    PRESENCE_CHECK_INSTRUCTIONS,
    WELCOME_INSTRUCTIONS,
    build_system_prompt,
)
from app.ai.voice_agent.whisper_stt import OpenRouterWhisperSTT

from app.core.config import settings

_logger = logging.getLogger("russel.voice_agent")

CONCLUDE_DISCONNECT_DELAY_SECONDS = 10
"""Delay between conclude_interview firing and forcibly disconnecting the room,
so the agent's closing line has time to finish playing over TTS."""


def _compute_remaining(start_time: float, duration_seconds: float) -> int:
    """Return remaining interview seconds (floored at 0)."""
    return round(max(0.0, duration_seconds - (time.time() - start_time)))


class InterviewerAgent(Agent):
    def __init__(
        self,
        job_post_data: str,
        room: rtc.Room,
        interview_id: str,
        duration_minutes: int = settings.INTERVIEW_DURATION_MINUTES,
        candidate_cv_text: str = "",
    ) -> None:
        self._duration_seconds = duration_minutes * 60
        self._start_time: float | None = None
        self._interrupted = asyncio.Event()
        self._interview_id = interview_id
        self._room = room
        self._concluded = False  # set when conclude_interview tool fires
        self._generation = 0
        """Bumped every time the LLM starts a new response attempt. Tags each
        assistant_chunk so the frontend can tell a superseded self-revision
        (whose audio never plays — the session cancels it) from the attempt
        that actually gets spoken, instead of concatenating both forever."""

        super().__init__(
            instructions=build_system_prompt(
                job_post_data, duration_minutes, candidate_cv_text
            )
        )

    async def on_enter(self) -> None:
        self._start_time = time.time()
        await self.session.generate_reply(instructions=WELCOME_INSTRUCTIONS)

    @function_tool(
        description=(
            "End the interview and record its outcome. Call this exactly once — "
            "AFTER delivering your final spoken message to the candidate. "
            "passed=True for normal completion or exceptional performance; "
            "passed=False for misconduct or repeated inability to answer."
        )
    )
    async def conclude_interview(self, passed: bool, reason: str) -> str:
        """Store the pass/fail outcome, signal the frontend, then disconnect the room."""
        store_conclude_result(self._interview_id, passed, reason)
        self._concluded = True  # stop no-response checker immediately
        _logger.info(
            "Interview %s concluded via tool — passed=%s reason=%s",
            self._interview_id, passed, reason,
        )

        async def _delayed_disconnect() -> None:
            # Give the closing line time to finish playing over TTS before
            # tearing down the room — disconnecting immediately can cut the
            # candidate's audio off mid-sentence.
            await asyncio.sleep(CONCLUDE_DISCONNECT_DELAY_SECONDS - 2)
            # Tell the frontend to leave the room so RoomEvent.Disconnected fires there.
            try:
                await self._room.local_participant.publish_data(
                    json.dumps({"role": "control", "event": "interview_ended", "passed": passed}).encode(),
                    reliable=True,
                )
            except Exception as exc:
                _logger.debug("Failed to publish interview_ended control event: %s", exc)

            await asyncio.sleep(2)  # give the frontend a few seconds to receive the event before disconnecting
            await self._room.disconnect()

        asyncio.create_task(_delayed_disconnect())
        return "Interview concluded."

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
        self._generation += 1
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
        generation = self._generation  # snapshot: this tts_node call belongs to this attempt

        async def _gated_text():
            async for segment in text:
                if self._interrupted.is_set():
                    break
                asyncio.ensure_future(self._publish_chunk(segment, generation))
                yield segment

        async for frame in Agent.default.tts_node(self, _gated_text(), model_settings):
            yield frame

    def mark_interrupted(self) -> None:
        self._interrupted.set()

    async def _publish_chunk(self, text: str, generation: int) -> None:
        try:
            await self._room.local_participant.publish_data(
                json.dumps({"role": "assistant_chunk", "text": text, "generation": generation}).encode(),
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
    get_agent=None,
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
        # Stop immediately when the agent's conclude_interview tool has fired.
        if get_agent is not None and getattr(get_agent(), "_concluded", False):
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
    job_post_data: str,
    interview_id: str,
    duration_minutes: int = settings.INTERVIEW_DURATION_MINUTES,
    no_response_timeout_seconds: int = 30,
    cancel_interview_on_no_response: int = 0,
    candidate_cv_text: str = "",
) -> tuple[list[dict], str | None]:
    """
    Run the voice interview session.
    Returns (conversation_history, terminated_reason).
    terminated_reason is None for normal completion, or a string if terminated early.
    """
    _logger.info("Voice agent starting — %d min", duration_minutes)

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

        remaining = _get_remaining()
        agent = interviewer_agent_ref[0]
        generation = agent._generation if agent is not None else 0
        msg = {"role": "assistant", "text": clean_text, "remaining_time": remaining, "generation": generation}
        conversation_history.append(msg)
        m, s = divmod(remaining, 60)
        display_text = f"{clean_text} [remaining: {m:02d}:{s:02d}]"
        asyncio.ensure_future(_publish({**msg, "text": display_text}))
        _logger.info("Agent said: %s", clean_text)

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
        vad = silero.VAD.load(
            activation_threshold=0.5,
        )
        session = AgentSession(
            vad=vad,
            stt=_build_stt_engine(vad),
            llm=openai.LLM(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY),
            tts=elevenlabs.TTS(
                model="eleven_flash_v2_5",
                voice_id=settings.ELEVENLABS_VOICE_ID,
                api_key=settings.ELEVENLABS_API_KEY,
                voice_settings=VoiceSettings(
                    speed=1.1,
                    stability=0.4,
                    similarity_boost=0.75,
                ),
            ),
            turn_handling={
                "endpointing": {"min_delay": 0, "max_delay": 1}, # (AFTER STT basically) how long the agent waits after it detects the user has stopped speaking
                "interruption": {
                    "enabled": True,
                    "min_duration": 0, # Minimum time the user must speak before it's considered a valid interruption.
                    "min_words": 1, # Minimum number of recognized words required to trigger an interruption.
                },
                "preemptive_generation": {"enabled": False}, # If enabled, the LLM starts generating a response before the user's turn is officially complete to reduce latency.
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
                get_agent=lambda: interviewer_agent_ref[0],
            )
        )

        interviewer_agent_ref[0] = InterviewerAgent(
            job_post_data, room, interview_id, duration_minutes, candidate_cv_text=candidate_cv_text
        )
        await session.start(
            agent=interviewer_agent_ref[0],
            room=room,
            room_options=RoomOptions(
                audio_input=AudioInputOptions(noise_cancellation=noise_cancellation.BVC()),
            ),
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
