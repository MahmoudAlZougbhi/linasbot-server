"""Guest chat: public access, 10-question / 50-word limits, no tool writes, real LLM path."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


class _FakeMsg:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMsg(content)


class _FakeUsage:
    prompt_tokens = 11
    completion_tokens = 22


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


@pytest.fixture()
def guest_client(tmp_path: Path):
    import modules.guest_ai_api  # noqa: F401
    from modules.core import app
    from services.guest_chat_store import GuestChatStore

    store = GuestChatStore(root=tmp_path / "guest_chat")

    async def _fake_create(**kwargs: Any) -> _FakeResponse:
        messages = kwargs.get("messages") or []
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = str(m.get("content") or "")
                break
        lower = user_text.lower()
        if "price" in lower or "pricing" in lower or "اشتراك" in lower:
            body = (
                "Pricing depends on your plan tier and included usage credits. "
                "Guest chat can’t bill you — sign in to see Billing & Usage for your workspace."
            )
        elif "instagram" in lower or "meta" in lower:
            body = (
                "Linas connects Meta (Instagram/Facebook) from Integrations. "
                "Comment automation stays gated until App Review + live_verified."
            )
        elif "content management" in lower or " cm" in lower or lower.strip() == "cm":
            body = (
                "AI Setup is where you configure what your customer AI knows — "
                "services, prices, FAQ, handoff — then validate and publish when ready."
            )
        else:
            body = (
                f"Linas AI helps with that specifically: {user_text[:80]}. "
                "After sign-in, System Copilot can operate setup for your workspace."
            )
        # Prove history was included when present.
        prior_users = [m for m in messages if m.get("role") == "user"]
        if len(prior_users) >= 2:
            body += " (continuing our earlier thread)"
        return _FakeResponse(body)

    fake_client = type(
        "C", (), {"chat": type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(_fake_create)})()})()}
    )()

    with patch("modules.guest_ai_api.guest_chat_store", store):
        with patch("services.guest_chat_store.guest_chat_store", store):
            with patch("services.llm_core_service.client", fake_client):
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


def test_guest_word_limit_allows_over_50(guest_client):
    """V2 removed the artificial 50-word ceiling; 51 words must be accepted."""
    client, _store = guest_client
    sid = "guest-test-session-words"
    client.post("/api/guest-ai/session", json={"guest_session_id": sid})
    long = " ".join(["word"] * 51)
    r = client.post(
        "/api/guest-ai/session/messages",
        json={"guest_session_id": sid, "content": long},
    )
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_guest_abuse_word_guard_still_rejects_huge(guest_client):
    client, _store = guest_client
    sid = "guest-test-session-huge"
    client.post("/api/guest-ai/session", json={"guest_session_id": sid})
    # Stay under pydantic body max while exceeding GUEST_MAX_WORDS (2000).
    huge = " ".join(["w"] * 2001)
    r = client.post(
        "/api/guest-ai/session/messages",
        json={"guest_session_id": sid, "content": huge},
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


@pytest.mark.asyncio
async def test_compose_guest_reply_uses_llm_not_canned_pitch():
    from services.guest_ai_service import FORBIDDEN_GUEST_TOOLS, compose_guest_reply

    async def _create(**kwargs: Any) -> _FakeResponse:
        assert kwargs.get("messages")
        assert kwargs["messages"][0]["role"] == "system"
        assert (
            "broken record" in kwargs["messages"][0]["content"] or "not a brochure" in kwargs["messages"][0]["content"]
        )
        return _FakeResponse("AI Setup lets you teach the AI your services and FAQs before publish.")

    fake = type(
        "C",
        (),
        {"chat": type("Ch", (), {"completions": type("Co", (), {"create": AsyncMock(side_effect=_create)})()})()},
    )()
    with patch("services.llm_core_service.client", fake):
        result = await compose_guest_reply("Explain AI Setup", language="en")
    assert result["tools_used"] == []
    assert FORBIDDEN_GUEST_TOOLS
    assert "AI Setup" in result["reply_text"]
    # Old canned sales intro must not be the reply body.
    assert not result["reply_text"].startswith("Linas AI is a business AI platform: connect channels")


def test_different_guest_questions_get_different_answers(guest_client):
    client, _store = guest_client
    sid = "guest-test-session-variety"
    client.post("/api/guest-ai/session", json={"guest_session_id": sid, "language": "en"})

    r1 = client.post(
        "/api/guest-ai/session/messages",
        json={"guest_session_id": sid, "content": "What is your pricing?"},
    )
    r2 = client.post(
        "/api/guest-ai/session/messages",
        json={"guest_session_id": sid, "content": "How does Instagram / Meta integration work?"},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    a1 = r1.json()["message"]["content"]
    a2 = r2.json()["message"]["content"]
    assert a1 != a2
    assert "pricing" in a1.lower() or "plan" in a1.lower() or "credit" in a1.lower()
    assert "instagram" in a2.lower() or "meta" in a2.lower()
    # Follow-up should see history (fake model appends marker when >=2 user msgs in prompt).
    assert "continuing our earlier thread" in a2


def test_guest_llm_failure_surfaces_error_no_canned_fallback(guest_client):
    client, store = guest_client
    sid = "guest-test-session-fail"

    async def _boom(**_kwargs: Any) -> Any:
        raise RuntimeError("simulated_provider_down")

    client.post("/api/guest-ai/session", json={"guest_session_id": sid, "language": "en"})
    boom = type(
        "C", (), {"chat": type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(_boom)})()})()}
    )()
    with patch("services.llm_core_service.client", boom):
        r = client.post(
            "/api/guest-ai/session/messages",
            json={"guest_session_id": sid, "content": "What is Linas?"},
        )
    assert r.status_code == 503
    detail = r.json().get("detail") or {}
    assert detail.get("error") == "guest_model_unavailable"
    assert "business AI platform: connect channels" not in str(detail).lower()
    assert "sales_intro" not in str(detail).lower()
    session = store.get(sid)
    assert session is not None
    assert session.questions_used == 0
    assert len([m for m in session.messages if m.role == "user"]) == 0


@pytest.mark.asyncio
async def test_guest_llm_uses_gpt5_safe_params_not_legacy_max_tokens():
    """gpt-5-mini rejects max_tokens + non-default temperature (prod BadRequest root cause)."""
    from services.guest_ai_service import compose_guest_reply

    captured: dict[str, Any] = {}

    async def _create(**kwargs: Any) -> _FakeResponse:
        captured.update(kwargs)
        return _FakeResponse("Instagram DMs connect via Meta Integrations after you subscribe.")

    fake = type(
        "C",
        (),
        {"chat": type("Ch", (), {"completions": type("Co", (), {"create": AsyncMock(side_effect=_create)})()})()},
    )()
    with patch("services.llm_core_service.client", fake):
        with patch.dict("os.environ", {"LINAS_GUEST_MODEL": "gpt-5-mini"}, clear=False):
            result = await compose_guest_reply("How do Instagram DMs work?", language="en")
    assert "Instagram" in result["reply_text"]
    assert "max_tokens" not in captured
    # Reasoning models need a high completion floor or OpenAI returns empty content.
    assert int(captured.get("max_completion_tokens") or 0) >= 2048
    assert captured.get("reasoning_effort") == "low"
    assert "temperature" not in captured
    assert captured.get("model") == "gpt-5-mini"


def test_build_chat_completion_kwargs_gpt5_vs_legacy():
    from services.llm_core_service import build_chat_completion_kwargs

    gpt5 = build_chat_completion_kwargs(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
        temperature=0.7,
    )
    assert gpt5["max_completion_tokens"] >= 2048
    assert gpt5.get("reasoning_effort") == "low"
    assert "max_tokens" not in gpt5
    assert "temperature" not in gpt5

    legacy = build_chat_completion_kwargs(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
        temperature=0.7,
    )
    assert legacy["max_tokens"] == 100
    assert legacy["temperature"] == 0.7
    assert "max_completion_tokens" not in legacy
    assert "reasoning_effort" not in legacy


def test_guest_routes_are_public():
    from modules.api_security import is_public_api

    assert is_public_api("POST", "/api/guest-ai/session")
    assert is_public_api("POST", "/api/guest-ai/session/messages")
    assert is_public_api("GET", "/api/guest-ai/session")
    assert not is_public_api("POST", "/api/owner-ai/conversations")
