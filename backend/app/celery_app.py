import os

# Must be set before numpy (pulled in transitively by the AI/embedding stack) is imported
# anywhere in the process — OpenBLAS reads this at import time to size its thread pool.
# Uncapped, it spawns a thread per core, which under Celery's Windows --pool=solo runner
# has been observed to exhaust memory ("OpenBLAS error: Memory allocation still failed").
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import logging

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "russel_ai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
    include=["app.tasks.written_test_tasks", "app.tasks.ats_rerun_tasks", "app.tasks.interview_scheduling_tasks"],
)


@worker_process_init.connect
def _warm_up_voice_agent_imports(**_kwargs) -> None:
    """LiveKit's voice plugins (Deepgram, ElevenLabs, etc. — see
    app/ai/voice_agent/agent.py) register themselves the moment their module is first
    imported, and that registration hard-requires the process's main thread. Left
    alone, that first import happens lazily inside run_scheduled_interview_task
    (interview_scheduling_tasks.py) the first time a scheduled interview fires —
    which Celery runs off the main thread, crashing with "Plugins must be registered
    on the main thread" before start_scheduled_interview ever runs.

    worker_process_init fires once, synchronously, on the worker process's actual main
    thread right at startup — importing the module here instead forces plugin
    registration to happen safely, before any task (scheduled or otherwise) ever needs
    it. FastAPI doesn't need this because it already imports the same module at
    startup, on its own main thread.
    """
    try:
        import app.ai.voice_agent.agent  # noqa: F401
        logger.info("celery_app: voice agent plugins warmed up on worker main thread")
    except Exception:
        logger.exception("celery_app: failed to warm up voice agent plugin imports")
