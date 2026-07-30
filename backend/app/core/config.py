from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent.parent / ".env"

# LangSmith's tracing (LANGCHAIN_TRACING_V2 etc.) is read directly from os.environ by the
# langsmith/langchain internals, not through this Settings object — unlike every other setting
# here, which callers read via `settings.X` and pass explicitly (see get_llm below). Exporting
# the .env file into the real process environment is the only way tracing auto-activates.
load_dotenv(_ENV_FILE)


class Settings(BaseSettings):
    PROJECT_NAME: str = "Russel.AI"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.4-mini"
    LLAMA_CLOUD_API_KEY: str = ""
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    DEEPGRAM_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    WHISPER_MODEL: str = "openai/whisper-large-v3-turbo"
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = "onwK4e9ZLuTAKqWW03F9"
    # Kill-switch: set to False in dev/test to disable all fail-case enforcement
    ENABLE_FAIL_CASES: bool = True
    # No-response timeout: seconds of silence before the AI checks if candidate is still present
    NO_RESPONSE_TIMEOUT_SECONDS: int = 30
    # How many no-response triggers before cancelling the interview (0 = never cancel)
    CANCEL_INTERVIEW_ON_NO_RESPONSE: int = 0
    # Global interview duration (minutes) — fallback when a round's
    # InterviewRounds.time_limit_minutes is NULL
    INTERVIEW_DURATION_MINUTES: int = 45
    # When True, /status-stream's SSE wait timeout extends to 1 hour so a
    # manual debugger pause mid-flow doesn't get cut off by the normal timeout.
    DEBUG_MODE: bool = False
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    # Google Calendar OAuth (recruiter interview scheduling — see
    # app/services/google_calendar_service.py). GOOGLE_REDIRECT_URI must exactly match
    # an "Authorized redirect URI" configured on the Google Cloud OAuth client.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/google-calendar/callback"
    # Where the OAuth callback (a backend redirect) sends the recruiter's browser back
    # to — must be the frontend's own origin, not the backend's, since a relative
    # redirect from FastAPI would otherwise resolve against this API's own host.
    FRONTEND_URL: str = "http://localhost:5173"
    # How long the AI interviewer waits in the room for the candidate to join a
    # scheduled interview before marking it a no-show (see
    # app/tasks/interview_scheduling_tasks.py). +0.5 min (30s) over the intended
    # window compensates for scheduling_service.EARLY_DISPATCH_SECONDS — the agent's
    # wait clock actually starts 30s before the scheduled time, so this keeps the
    # candidate's effective join window measured from the real scheduled time unchanged.
    SCHEDULED_INTERVIEW_JOIN_WINDOW_MINUTES: float = 1.5
    # Timezone auto-scheduling falls back to when a round has never been manually
    # scheduled before (so there's no prior scheduled_timezone to reuse). Manual
    # scheduling always uses whatever timezone the recruiter picks in the UI.
    DEFAULT_SCHEDULING_TIMEZONE: str = "UTC"
    # LangSmith tracing for the ATS LLM call (see ats_service._invoke_ats_llm)
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "russell-recruiter-ats"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    # SMTP credentials for sending signup OTP verification emails (see app/core/mailer.py).
    # Empty SMTP_HOST means send_email() logs instead of sending — safe default for dev.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@russel.ai"
    # Public HTTPS URL Google POSTs Calendar push notifications to — must resolve to
    # this backend's /api/google-calendar/webhook route (see google_calendar_service.watch_calendar).
    GOOGLE_WEBHOOK_URL: str = ""

    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8")


settings = Settings()


def get_llm(temperature: float = 0, **kwargs) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=temperature,
        **kwargs,
    )
