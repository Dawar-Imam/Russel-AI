import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.events import subscribe_ats_completed

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Minimal in-memory WebSocket registry keyed by application_id.

    Single-process only (no pub/sub backing) — fine for now since there's one
    API process; if that changes, this needs a broker-backed fanout instead.
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, application_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(application_id, []).append(websocket)

    def disconnect(self, application_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(application_id)
        if conns and websocket in conns:
            conns.remove(websocket)
            if not conns:
                del self._connections[application_id]

    async def send(self, application_id: str, payload: dict) -> int:
        """No-op if no client is connected for this application_id — the frontend's
        existing polling remains the fallback path regardless.

        Returns the number of connections the payload was actually delivered to, so
        callers can log whether anyone was listening.
        """
        sent = 0
        for websocket in list(self._connections.get(application_id, [])):
            try:
                await websocket.send_json(payload)
                sent += 1
            except Exception:
                logger.warning("ws: failed to send to a connection for application_id=%s, dropping it", application_id)
                self.disconnect(application_id, websocket)
        return sent


manager = ConnectionManager()


async def _forward_ats_completed(application_id: str, payload: dict) -> None:
    sent_count = await manager.send(application_id, payload)
    status = payload.get("status")
    if sent_count > 0:
        logger.info(f"WS event emitted for application_id={application_id}, status={status}")
    else:
        logger.info(f"WS event skipped (no active connection) for application_id={application_id}, status={status}")


subscribe_ats_completed(_forward_ats_completed)


@router.websocket("/ws/applications/{application_id}")
async def applications_ws(websocket: WebSocket, application_id: str) -> None:
    await manager.connect(application_id, websocket)
    try:
        while True:
            # Connection is server-push only; just keep it open until the client disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(application_id, websocket)
