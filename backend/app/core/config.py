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
    # Global interview duration (minutes)
    INTERVIEW_DURATION_MINUTES: int = 1
    # When True, /status-stream's SSE wait timeout extends to 1 hour so a
    # manual debugger pause mid-flow doesn't get cut off by the normal timeout.
    DEBUG_MODE: bool = False
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    # LangSmith tracing for the ATS LLM call (see ats_service._invoke_ats_llm)
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "russell-recruiter-ats"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8")


settings = Settings()


def get_llm(temperature: float = 0, **kwargs) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=temperature,
        **kwargs,
    )
