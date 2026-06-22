import asyncio
import json
import logging

from livekit import rtc
from livekit.agents import Agent, AgentSession
from livekit.agents.utils import http_context
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import deepgram, openai, silero

from app.core.config import settings
from app.schemas.interviews import QuestionItem

_logger = logging.getLogger("russel.voice_agent")


class InterviewerAgent(Agent):
    def __init__(self, questions: list[QuestionItem]) -> None:
        questions_block = "\n".join(f"{i + 1}. {q.question_text}" for i, q in enumerate(questions))
        super().__init__(
            instructions=(
                "You are Russel, an AI interviewer conducting a voice interview. "
                "Ask the candidate the following questions one at a time, in order. "
                "Wait for the candidate to finish answering before moving on. "
                "Briefly acknowledge each answer, then ask the next question. "
                "Keep all responses short and conversational.\n\n"
                f"Questions:\n{questions_block}"
            )
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions=(
                "Warmly welcome the candidate to their interview. Introduce "
                "yourself as Russel, an AI interviewer. Let them know the interview "
                "will consist of a few short questions and they should answer naturally. "
                "Then immediately ask the first interview question."
            )
        )


async def run_voice_agent(
    room: rtc.Room,
    questions: list[QuestionItem],
) -> list[dict]:
    """Run the voice interview session and return the full conversation history."""
    _logger.info("Voice agent starting — %d questions", len(questions))

    conversation_history: list[dict] = []

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
        msg = {"role": "assistant", "text": text.strip()}
        conversation_history.append(msg)
        asyncio.ensure_future(_publish(msg))
        _logger.info("Agent said: %s", text.strip())

    def _on_user_transcript(ev) -> None:
        if not ev.is_final or not ev.transcript.strip():
            return
        msg = {"role": "user", "text": ev.transcript.strip()}
        conversation_history.append(msg)
        asyncio.ensure_future(_publish(msg))
        _logger.info("User said: %s", ev.transcript.strip())

    disconnected = asyncio.Event()
    room.on("disconnected")(lambda *_: disconnected.set())

    async with http_context.open():
        vad = silero.VAD.load()
        session = AgentSession(
            vad=vad,
            stt=deepgram.STT(model="nova-3", api_key=settings.DEEPGRAM_API_KEY),
            llm=openai.LLM(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY),
            tts=openai.TTS(model="gpt-4o-mini-tts", api_key=settings.OPENAI_API_KEY),
        )

        session.on("conversation_item_added")(_on_conversation_item)
        session.on("user_input_transcribed")(_on_user_transcript)

        await session.start(
            agent=InterviewerAgent(questions),
            room=room,
            room_options=RoomOptions(),
        )

        await disconnected.wait()

    _logger.info("Voice agent finished — %d conversation turns", len(conversation_history))
    return conversation_history
