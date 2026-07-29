"""Domain-event bus for "ATS finished for this application", backed by Redis pub/sub
so it works across process boundaries.

Lets the service layer announce this without importing the API/transport layer to do it
directly — the API layer subscribes from its side instead (see app/api/endpoints/ws.py)
— this inverts the app/services -> app/api dependency that existed before, where
application_service.py imported app.api.endpoints.ws directly.

Redis-backed (not a plain in-process list) because the actual work that completes an
ATS rerun runs inside the Celery worker process (app/tasks/ats_rerun_tasks.py), which
never shares memory with the FastAPI/uvicorn process holding the candidate's WebSocket
connection (app/api/endpoints/ws.py's ConnectionManager). A plain Python list of
subscribers only ever gets populated in the FastAPI process (ws.py's
subscribe_ats_completed call, which the Celery worker never imports), so
publish_ats_completed calling it directly from the worker process was a silent no-op —
nothing crashed, there was just nothing registered to call.

Deliberately uses the same plain sync redis client as app.services.ats_lock, not
redis.asyncio, on both the publish and listen sides: a redis.asyncio connection is bound
to whichever asyncio event loop was running when it first connected, and
ats_rerun_tasks._run_one_application runs each application on its own thread via
`asyncio.run(rerun_ats_and_persist(...))` — a fresh event loop per call. Sharing one
async client across those causes "RuntimeError: Event loop is closed" the moment a
second application's asyncio.run() reuses a connection opened under the first one's
already-closed loop. A sync client has no event-loop affinity, so it's safe from any
thread. The listener side runs the blocking sync pubsub.listen() loop on its own
background thread (started once in the FastAPI process — see app/main.py) and hands
each message to the FastAPI event loop via run_coroutine_threadsafe, since the actual
subscriber handlers (ws.py's ConnectionManager, an async WebSocket send) belong on that
loop.
"""
import asyncio
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable

from app.services.ats_lock import get_redis_client

logger = logging.getLogger(__name__)

AtsCompletedHandler = Callable[[str, dict], Awaitable[None]]
_ats_completed_subscribers: list[AtsCompletedHandler] = []

_ATS_COMPLETED_CHANNEL = "ats_completed_channel"
_LISTENER_RECONNECT_DELAY_SECONDS = 5

# Recruiter-side counterpart of the bus above, keyed by job_id instead of
# application_id — same Redis pub/sub reasoning applies (the Calendar webhook runs in
# the same FastAPI process here, but delete_scheduled_interview and any future
# Celery-side publisher need the same cross-process delivery), so this mirrors the
# ats_completed bus structurally rather than trying to generalize both into one, to
# avoid touching the already-working ATS pipeline.
JobUpdateHandler = Callable[[str, dict], Awaitable[None]]
_job_update_subscribers: list[JobUpdateHandler] = []

_JOB_UPDATE_CHANNEL = "job_update_channel"


def subscribe_ats_completed(handler: AtsCompletedHandler) -> None:
    _ats_completed_subscribers.append(handler)


async def publish_ats_completed(application_id: str, payload: dict) -> None:
    try:
        get_redis_client().publish(
            _ATS_COMPLETED_CHANNEL,
            json.dumps({"application_id": application_id, "payload": payload}),
        )
    except Exception:
        logger.exception("events: failed to publish ats_completed for application_id=%s", application_id)


async def _deliver_to_local_subscribers(application_id: str, payload: dict) -> None:
    for handler in _ats_completed_subscribers:
        try:
            await handler(application_id, payload)
        except Exception:
            logger.exception("events: ats_completed subscriber failed for application_id=%s", application_id)


def start_ats_completed_listener(loop: asyncio.AbstractEventLoop) -> None:
    """Starts the Redis-subscriber background thread — call once, at FastAPI app
    startup (see app/main.py), passing its running event loop. No-op in the Celery
    worker process (nothing there ever calls this), which is fine: the worker only ever
    publishes, it never needs local subscribers of its own.
    """

    def _run() -> None:
        redis_client = get_redis_client()
        while True:
            try:
                pubsub = redis_client.pubsub()
                pubsub.subscribe(_ATS_COMPLETED_CHANNEL)
                for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        data = json.loads(message["data"])
                        asyncio.run_coroutine_threadsafe(
                            _deliver_to_local_subscribers(data["application_id"], data["payload"]),
                            loop,
                        )
                    except Exception:
                        logger.exception("events: failed to process an ats_completed message")
            except Exception:
                logger.exception(
                    "events: ats_completed listener crashed — reconnecting in %ds",
                    _LISTENER_RECONNECT_DELAY_SECONDS,
                )
                time.sleep(_LISTENER_RECONNECT_DELAY_SECONDS)

    threading.Thread(target=_run, name="ats-completed-listener", daemon=True).start()


def subscribe_job_update(handler: JobUpdateHandler) -> None:
    _job_update_subscribers.append(handler)


async def publish_job_update(job_id: str, payload: dict) -> None:
    try:
        get_redis_client().publish(
            _JOB_UPDATE_CHANNEL,
            json.dumps({"job_id": job_id, "payload": payload}),
        )
    except Exception:
        logger.exception("events: failed to publish job_update for job_id=%s", job_id)


async def _deliver_to_job_update_subscribers(job_id: str, payload: dict) -> None:
    for handler in _job_update_subscribers:
        try:
            await handler(job_id, payload)
        except Exception:
            logger.exception("events: job_update subscriber failed for job_id=%s", job_id)


def start_job_update_listener(loop: asyncio.AbstractEventLoop) -> None:
    """Recruiter-side counterpart of start_ats_completed_listener above — same
    call-once-at-startup contract, see app/main.py."""

    def _run() -> None:
        redis_client = get_redis_client()
        while True:
            try:
                pubsub = redis_client.pubsub()
                pubsub.subscribe(_JOB_UPDATE_CHANNEL)
                for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        data = json.loads(message["data"])
                        asyncio.run_coroutine_threadsafe(
                            _deliver_to_job_update_subscribers(data["job_id"], data["payload"]),
                            loop,
                        )
                    except Exception:
                        logger.exception("events: failed to process a job_update message")
            except Exception:
                logger.exception(
                    "events: job_update listener crashed — reconnecting in %ds",
                    _LISTENER_RECONNECT_DELAY_SECONDS,
                )
                time.sleep(_LISTENER_RECONNECT_DELAY_SECONDS)

    threading.Thread(target=_run, name="job-update-listener", daemon=True).start()
