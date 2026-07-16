import os

# Must be set before numpy (pulled in transitively by the AI/embedding stack) is imported
# anywhere in the process — OpenBLAS reads this at import time to size its thread pool.
# Uncapped, it spawns a thread per core, which under Celery's Windows --pool=solo runner
# has been observed to exhaust memory ("OpenBLAS error: Memory allocation still failed").
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "russel_ai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
    include=["app.tasks.written_test_tasks", "app.tasks.ats_rerun_tasks"],
)
