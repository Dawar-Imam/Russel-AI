import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.voice_agent.room_connection import (
    BACKEND_DIR,
    CreateRoomResponse,
    create_room,
    enter_person_and_agent_in_room,
)


def _make_token_mock(jwt_value: str = "mock.jwt.token") -> MagicMock:
    m = MagicMock()
    m.with_identity.return_value = m
    m.with_name.return_value = m
    m.with_grants.return_value = m
    m.to_jwt.return_value = jwt_value
    return m


def _patch_livekit(jwt_value: str = "mock.jwt.token"):
    """Returns a context-manager stack that mocks LiveKitAPI and AccessToken."""
    mock_lkapi = AsyncMock()
    mock_lkapi_cls = MagicMock(return_value=mock_lkapi)

    token_instance = _make_token_mock(jwt_value)
    mock_access_token_cls = MagicMock(return_value=token_instance)

    return mock_lkapi_cls, mock_access_token_cls


# ── create_room ───────────────────────────────────────────────────────────────

def test_create_room_returns_correct_shape():
    mock_lkapi_cls, mock_access_token_cls = _patch_livekit()

    with (
        patch("app.ai.voice_agent.room_connection.LiveKitAPI", mock_lkapi_cls),
        patch("app.ai.voice_agent.room_connection.AccessToken", mock_access_token_cls),
    ):
        result = asyncio.run(create_room())

    assert isinstance(result, CreateRoomResponse)
    assert result.room_name.startswith("interview-room-")
    assert result.identity.startswith("candidate-")
    assert result.token == "mock.jwt.token"


def test_create_room_creates_livekit_room():
    mock_lkapi_cls, mock_access_token_cls = _patch_livekit()
    mock_lkapi_instance = mock_lkapi_cls.return_value

    with (
        patch("app.ai.voice_agent.room_connection.LiveKitAPI", mock_lkapi_cls),
        patch("app.ai.voice_agent.room_connection.AccessToken", mock_access_token_cls),
    ):
        result = asyncio.run(create_room())

    mock_lkapi_instance.room.create_room.assert_awaited_once()
    mock_lkapi_instance.aclose.assert_awaited_once()


def test_create_room_unique_names():
    mock_lkapi_cls, mock_access_token_cls = _patch_livekit()

    with (
        patch("app.ai.voice_agent.room_connection.LiveKitAPI", mock_lkapi_cls),
        patch("app.ai.voice_agent.room_connection.AccessToken", mock_access_token_cls),
    ):
        r1 = asyncio.run(create_room())
        r2 = asyncio.run(create_room())

    assert r1.room_name != r2.room_name
    assert r1.identity != r2.identity


# ── enter_person_and_agent_in_room ────────────────────────────────────────────

def test_enter_person_and_agent_in_room_returns_room_response():
    mock_lkapi_cls, mock_access_token_cls = _patch_livekit()
    mock_popen = MagicMock()

    with (
        patch("app.ai.voice_agent.room_connection.LiveKitAPI", mock_lkapi_cls),
        patch("app.ai.voice_agent.room_connection.AccessToken", mock_access_token_cls),
        patch("app.ai.voice_agent.room_connection.subprocess.Popen", mock_popen),
    ):
        result = asyncio.run(enter_person_and_agent_in_room())

    assert isinstance(result, CreateRoomResponse)
    assert result.room_name.startswith("interview-room-")
    assert result.identity.startswith("candidate-")


def test_enter_person_and_agent_in_room_starts_agent_subprocess():
    mock_lkapi_cls, mock_access_token_cls = _patch_livekit()
    mock_popen = MagicMock()

    with (
        patch("app.ai.voice_agent.room_connection.LiveKitAPI", mock_lkapi_cls),
        patch("app.ai.voice_agent.room_connection.AccessToken", mock_access_token_cls),
        patch("app.ai.voice_agent.room_connection.subprocess.Popen", mock_popen),
    ):
        asyncio.run(enter_person_and_agent_in_room())

    mock_popen.assert_called_once_with(
        [sys.executable, "-m", "app.ai.voice_agent.agent", "start"],
        cwd=str(BACKEND_DIR),
    )


def test_enter_person_and_agent_in_room_backend_dir_is_backend_root():
    # BACKEND_DIR must point to the backend/ folder (where uv/pyproject.toml live).
    assert (BACKEND_DIR / "pyproject.toml").exists(), (
        f"BACKEND_DIR {BACKEND_DIR} does not contain pyproject.toml"
    )
