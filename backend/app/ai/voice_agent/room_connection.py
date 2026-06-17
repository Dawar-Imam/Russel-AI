import subprocess
import sys
import uuid
from pathlib import Path

from livekit.api import AccessToken, CreateRoomRequest, LiveKitAPI, VideoGrants
from pydantic import BaseModel

from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent


class CreateRoomResponse(BaseModel):
    url: str
    token: str
    room_name: str
    identity: str


async def create_room() -> CreateRoomResponse:
    room_name = f"interview-room-{uuid.uuid4().hex[:8]}"
    identity = f"candidate-{uuid.uuid4().hex[:8]}"

    lkapi = LiveKitAPI(settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    await lkapi.room.create_room(CreateRoomRequest(name=room_name))
    await lkapi.aclose()

    token = (
        AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True))
    )

    return CreateRoomResponse(
        url=settings.LIVEKIT_URL,
        token=token.to_jwt(),
        room_name=room_name,
        identity=identity,
    )


async def enter_person_and_agent_in_room() -> CreateRoomResponse:
    room_response = await create_room() # where the candidate will join

    subprocess.Popen(
        [sys.executable, "-m", "app.ai.voice_agent.agent", "start"],
        cwd=str(BACKEND_DIR),
    )

    return room_response
