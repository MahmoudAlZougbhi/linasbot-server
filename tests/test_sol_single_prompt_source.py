"""Freeze: Sol compose has one portal persona source — no SYSTEM_V2 + SYSTEM_PROMPT."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.owner_copilot.brain_support import _build_messages
from services.owner_copilot.sol_identity import compose_sol_system, sol_basics_configured
from services.owner_copilot.sol_runtime_stub import SOL_RUNTIME_STUB
from services.owner_copilot.sol_seed import default_sol_basics_payload

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = (
    ROOT / "services/owner_copilot/brain_support.py",
    ROOT / "services/owner_copilot/context.py",
    ROOT / "services/owner_copilot/brain_stream_body.py",
)


def test_system_v2_and_system_prompt_identifiers_gone_from_compose() -> None:
    hits: list[str] = []
    for path in COMPOSE_FILES:
        text = path.read_text(encoding="utf-8")
        if "SYSTEM_V2" in text:
            hits.append(f"{path.name}:SYSTEM_V2")
        if "SYSTEM_PROMPT" in text:
            hits.append(f"{path.name}:SYSTEM_PROMPT")
    assert not hits, hits


def test_compose_uses_portal_payload_only() -> None:
    payload = default_sol_basics_payload()
    assert sol_basics_configured(payload) is True
    block = compose_sol_system(payload)
    assert SOL_RUNTIME_STUB in block
    assert "You are Sol" in block or "Sol" in block
    assert block.count(SOL_RUNTIME_STUB) == 1
    assert "one brain for the authenticated" not in block
    msgs = _build_messages(
        context={
            "sol_system": block,
            "reply_language": "en",
            "account_summary": {},
            "knowledge_block": "EVIDENCE (published sol_app_knowledge, targeted — not a full dump):",
        },
        user_text="hello",
    )
    system_roles = [m for m in msgs if m.get("role") == "system"]
    assert len(system_roles) == 1
    content = str(system_roles[0].get("content") or "")
    assert content.count(SOL_RUNTIME_STUB) == 1
    assert "You are Linas AI System Copilot — one brain" not in content
    assert "You are Linas AI System Copilot — the brain of the Linas AI app" not in content


def test_empty_portal_is_unconfigured() -> None:
    assert sol_basics_configured({}) is False
    assert sol_basics_configured({"assistant_name": ""}) is False


def test_sol_sections_are_not_customer_retrieve_families() -> None:
    from services.ai_setup.constants import OWNER_ONLY_CM_SECTIONS

    src = (ROOT / "services/brain/retrieve/cards.py").read_text(encoding="utf-8")
    for section in OWNER_ONLY_CM_SECTIONS:
        assert f'"{section}"' not in src
        assert f"'{section}'" not in src


@pytest.mark.asyncio
async def test_unconfigured_sol_fail_soft_skips_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot.brain_stream_body import _iter_owner_turn_v2_events_body

    called = {"n": 0}

    async def _fake_round(**_k):
        called["n"] += 1
        yield ("delta", "should-not-run")

    monkeypatch.setattr("services.owner_copilot.brain_stream_body.iter_sol_tool_round", _fake_round)
    monkeypatch.setattr(
        "services.owner_copilot.brain_stream_body.pack_owner_turn_context",
        lambda **_: {
            "sol_system": "",
            "sol_unconfigured": True,
            "account_summary": {"setup_stage": "new"},
            "reply_language": "en",
        },
    )
    events = []
    async for ev in _iter_owner_turn_v2_events_body(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="hello",
    ):
        events.append(ev.type)
    assert called["n"] == 0
    assert "delta" in events
    assert events[-1] == "done"
