import asyncio
import json
import logging

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions
from livekit.plugins import deepgram, openai, silero

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_logger = logging.getLogger("russel.voice_agent")

DEFAULT_QUESTIONS = [
    "Can you tell me a bit about yourself and your background?",
    "What interests you about this role?",
    "Describe a challenging project you've worked on recently.",
    "How do you approach debugging a difficult issue?",
    "Tell me about a time you disagreed with a teammate. How did you handle it?",
    "What are your strongest technical skills?",
    "How do you stay up to date with new technologies?",
    "Describe your experience working in a team environment.",
    "What's a mistake you made and what did you learn from it?",
    "Do you have any questions for us?",
]


class InterviewerAgent(Agent):
    def __init__(self, questions: list[str]) -> None:
        questions_block = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
        super().__init__(
            instructions=(
                "You are Russel, an AI interviewer. You are conducting a voice interview. "
                "Ask the candidate the following questions one at a time, in order. "
                "Wait for the candidate to finish answering before moving on. "
                "Briefly acknowledge each answer, then ask the next question. "
                "Keep all responses short and conversational.\n\n"
                f"Questions:\n{questions_block}"
            )
        )

    async def on_enter(self) -> None:
        # Commented out: agent_ready control signal
        # await self.session.room.local_participant.publish_data(
        #     json.dumps({"type": "agent_ready"}),
        #     topic="control",
        # )
        await self.session.generate_reply(
            instructions=(
                "Warmly welcome the candidate to their interview. Introduce "
                "yourself as Russel, an AI interviewer. Let them know the interview "
                "will consist of a few short questions and they should answer naturally. "
                "Then immediately ask the first interview question."
            )
        )


def prewarm(proc: agents.JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: agents.JobContext) -> None:
    questions = DEFAULT_QUESTIONS
    if ctx.job.metadata:
        try:
            questions = json.loads(ctx.job.metadata).get("questions", DEFAULT_QUESTIONS)
        except (json.JSONDecodeError, AttributeError):
            pass

    _logger.info("Job received — %d questions", len(questions))

    await ctx.connect()

    candidate_answers: list[str] = []
    vad: silero.VAD = ctx.proc.userdata["vad"]

    session = AgentSession(
        vad=vad,
        stt=deepgram.STT(model="nova-3"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=openai.TTS(model="gpt-4o-mini-tts"),
    )

    def _on_user_transcript(ev) -> None:
        if not ev.is_final or not ev.transcript.strip():
            return

        candidate_answers.append(ev.transcript)
        _logger.info("Answer %d/%d collected", len(candidate_answers), len(questions))

        if len(candidate_answers) >= len(questions):
            async def _publish_answers() -> None:
                try:
                    await ctx.room.local_participant.publish_data(
                        json.dumps({
                            "type": "interview_completed",
                            "answers": candidate_answers,
                        }),
                        topic="answers",
                    )
                    _logger.info("Published %d answers to data channel", len(candidate_answers))
                except Exception as exc:
                    _logger.error("Failed to publish answers: %s", exc)

            asyncio.ensure_future(_publish_answers())

        # Commented out: transcript publishing to frontend
        # async def _publish_transcript() -> None:
        #     await ctx.room.local_participant.publish_data(
        #         json.dumps({"role": "user", "text": ev.transcript}),
        #         topic="transcript",
        #     )
        # asyncio.ensure_future(_publish_transcript())

    session.on("user_input_transcribed")(_on_user_transcript)

    # Commented out: assistant transcript publishing to frontend
    # @session.on("conversation_item_added")
    # def on_conversation_item(ev) -> None:
    #     item = ev.item
    #     if not isinstance(item, ChatMessage) or item.role != "assistant":
    #         return
    #     text = item.text_content
    #     if not text or not text.strip():
    #         return
    #     async def _publish() -> None:
    #         await ctx.room.local_participant.publish_data(
    #             json.dumps({"role": "assistant", "text": text}),
    #             topic="transcript",
    #         )
    #     asyncio.ensure_future(_publish())

    await session.start(
        agent=InterviewerAgent(questions),
        room=ctx.room,
        room_input_options=RoomInputOptions(),
    )


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )
