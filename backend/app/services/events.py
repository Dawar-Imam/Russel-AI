"""Lightweight in-process domain-event bus.

Lets the service layer announce things that happened (e.g. "ATS finished for
this application") without importing the API/transport layer to do it. The
API layer subscribes from its side instead (see app/api/endpoints/ws.py) —
this inverts the app/services -> app/api dependency that existed before,
where application_service.py imported app.api.endpoints.ws directly.
"""
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

AtsCompletedHandler = Callable[[str, dict], Awaitable[None]]
_ats_completed_subscribers: list[AtsCompletedHandler] = []


def subscribe_ats_completed(handler: AtsCompletedHandler) -> None:
    _ats_completed_subscribers.append(handler)


async def publish_ats_completed(application_id: str, payload: dict) -> None:
    for handler in _ats_completed_subscribers:
        try:
            await handler(application_id, payload)
        except Exception:
            logger.exception("events: ats_completed subscriber failed for application_id=%s", application_id)
