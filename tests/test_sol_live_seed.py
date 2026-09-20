"""Empty tenant owner chat auto-publishes seed Sol and does not stick on unconfigured."""

from __future__ import annotations

from typing import Any

import pytest

from services.owner_copilot.sol_identity import load_sol_identity, sol_basics_configured
from services.owner_copilot.sol_runtime_stub import SOL_UNCONFIGURED_AR, SOL_UNCONFIGURED_EN

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


@pytest.mark.asyncio
async def test_ensure_publishes_seed_when_missing(v2_env: Any) -> None:
    from services.owner_copilot.sol_ensure import ensure_published_sol_basics

    tid = "t_sol_seed_empty"
    assert sol_basics_configured(load_sol_identity(tid).get("payload") or {}) is False
    ok = await ensure_published_sol_basics(tid)
    assert ok is True
    identity = load_sol_identity(tid)
    assert identity["configured"] is True
    assert sol_basics_configured(identity["payload"]) is True
    again = await ensure_published_sol_basics(tid)
    assert again is True


@pytest.mark.asyncio
async def test_owner_kifak_reaches_sol_not_unconfigured(v2_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot.brain_stream_body import _iter_owner_turn_v2_events_body

    class _Round:
        tool_calls: list[Any] = []
        content = "Ahlan, I'm Sol."

    async def _fake_round(**_k: Any):
        yield ("delta", "Ahlan, I'm Sol.")
        yield ("done_round", _Round())

    monkeypatch.setattr("services.owner_copilot.brain_stream_body.iter_sol_tool_round", _fake_round)
    events: list[Any] = []
    async for ev in _iter_owner_turn_v2_events_body(
        tenant_id="t_sol_kifak",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="kifak",
        reply_language="ar",
    ):
        events.append(ev)
    done = next(ev for ev in events if ev.type == "done")
    assert done.payload.get("reason") != "sol_unconfigured"
    reply = str(done.payload.get("reply_text") or "")
    assert SOL_UNCONFIGURED_AR not in reply
    assert SOL_UNCONFIGURED_EN not in reply
    assert "Sol" in reply
    deltas = [str((ev.payload or {}).get("text") or "") for ev in events if ev.type == "delta"]
    assert any("Sol" in part for part in deltas)


def test_sol_ensure_does_not_revive_system_novels() -> None:
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "services/owner_copilot/sol_ensure.py").read_text(encoding="utf-8")
    assert "SYSTEM_V2" not in src
    assert "SYSTEM_PROMPT" not in src
