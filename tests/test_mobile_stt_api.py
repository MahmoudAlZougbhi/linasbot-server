"""Mobile /api/mobile/transcribe speech-to-text endpoint."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api_security import DashboardAuthMiddleware
from services.dashboard_session_service import SESSION_COOKIE_NAME, session_service


@pytest.fixture()
def stt_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import modules.mobile_stt_api as stt_mod

    app = FastAPI()
    app.add_middleware(DashboardAuthMiddleware)
    app.add_api_route(
        "/api/mobile/transcribe",
        stt_mod.mobile_transcribe,
        methods=["POST"],
    )

    fake_result = SimpleNamespace(text="  مرحبا من الصوت  ")
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(
        "services.llm_core_service.client",
        fake_client,
        raising=False,
    )
    # Ensure import path used inside handler sees the mock.
    import services.llm_core_service as llm

    monkeypatch.setattr(llm, "client", fake_client)

    return TestClient(app)


def test_mobile_transcribe_requires_auth(stt_client: TestClient) -> None:
    response = stt_client.post(
        "/api/mobile/transcribe",
        files={"audio": ("voice.m4a", BytesIO(b"fake-audio-bytes"), "audio/mp4")},
    )
    assert response.status_code == 401


def test_mobile_transcribe_returns_text(stt_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    session = session_service.create_session(
        user_id="u-stt",
        email="stt@example.com",
        role="admin",
        permissions=None,
        tenant_id="linas",
        password_epoch=0,
    )
    token = session_service.cookie_value_for(session)

    import services.llm_core_service as llm

    create = llm.client.audio.transcriptions.create

    response = stt_client.post(
        "/api/mobile/transcribe",
        headers={"Authorization": f"Bearer {token}"},
        files={"audio": ("voice.m4a", BytesIO(b"fake-audio-bytes-long-enough"), "audio/mp4")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["text"] == "مرحبا من الصوت"
    create.assert_awaited_once()
    kwargs = create.await_args.kwargs
    assert kwargs["file"].name.endswith(".m4a")


def test_safe_audio_filename() -> None:
    from modules.mobile_stt_api import _safe_audio_filename

    assert _safe_audio_filename("clip.m4a", "audio/mp4") == "voice.m4a"
    assert _safe_audio_filename("x.bin", "audio/webm") == "voice.webm"
    assert _safe_audio_filename(None, None) == "voice.m4a"
