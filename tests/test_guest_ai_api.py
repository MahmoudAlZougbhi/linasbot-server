"""Guest chat: public access, 10-question / 50-word limits, no tool writes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def guest_client(tmp_path: Path):
    import modules.guest_ai_api  # noqa: F401
    from modules.core import app
    from services.guest_chat_store import GuestChatStore

    store = GuestChatStore(root=tmp_path / "guest_chat")
    with patch("modules.guest_ai_api.guest_chat_store", store):
        with patch("services.guest_chat_store.guest_chat_store", store):
            yield TestClient(app), store


def test_guest_session_public_and_idempotent(guest_client):
    client, _store = guest_client
    sid = "guest-test-session-001"
    r1 = client.post("/api/guest-ai/session", json={"guest_session_id": sid, "language": "en"})
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["success"] is True
    assert body1["session"]["questions_remaining"] == 10
    assert body1["session"]["messages"][0]["role"] == "assistant"

    r2 = client.post("/api/guest-ai/session", json={"guest_session_id": sid, "language": "en"})
    assert r2.status_code == 200
    assert r2.json()["session"]["id"] == sid
    assert len(r2.json()["session"]["messages"]) == len(body1["session"]["messages"])


def test_guest_word_limit_rejected(guest_client):
    client, _store = guest_client
    sid = "guest-test-session-words"
    client.post("/api/guest-ai/session", json={"guest_session_id": sid})
    long = " ".join(["word"] * 51)
    r = client.post(
        "/api/guest-ai/session/messages",
        json={"guest_session_id": sid, "content": long},
    )
    assert r.status_code == 400
    detail = r.json().get("detail") or {}
    assert detail.get("error") == "word_limit" or "word" in str(detail).lower()


def test_guest_question_limit_and_no_tools(guest_client):
    client, store = guest_client
    sid = "guest-test-session-limit"
    client.post("/api/guest-ai/session", json={"guest_session_id": sid, "language": "en"})

    for i in range(10):
        r = client.post(
            "/api/guest-ai/session/messages",
            json={"guest_session_id": sid, "content": f"What do you offer number {i}?"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["meta"]["tools_used"] == []
        assert "propose_cm_patch" not in str(data).lower() or data["meta"]["tools_used"] == []

    r_gate = client.post(
        "/api/guest-ai/session/messages",
        json={"guest_session_id": sid, "content": "One more question please"},
    )
    assert r_gate.status_code == 200
    gated = r_gate.json()
    assert gated["success"] is False
    assert gated["code"] == "GUEST_QUESTION_LIMIT"
    assert gated["session"]["questions_remaining"] == 0

    session = store.get(sid)
    assert session is not None
    assert session.questions_used == 10


def test_compose_guest_reply_never_lists_tools():
    from services.guest_ai_service import FORBIDDEN_GUEST_TOOLS, compose_guest_reply

    result = compose_guest_reply("What do you offer for businesses?", language="en")
    assert result["tools_used"] == []
    assert FORBIDDEN_GUEST_TOOLS
    assert "Content Management" in result["reply_text"] or "business" in result["reply_text"].lower()


def test_guest_routes_are_public():
    from modules.api_security import is_public_api

    assert is_public_api("POST", "/api/guest-ai/session")
    assert is_public_api("POST", "/api/guest-ai/session/messages")
    assert is_public_api("GET", "/api/guest-ai/session")
    assert not is_public_api("POST", "/api/owner-ai/conversations")
