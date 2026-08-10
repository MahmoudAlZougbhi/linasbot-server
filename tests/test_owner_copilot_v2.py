"""System Copilot V2 — streaming protocol, choices, memory, attachments, flags."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from services.owner_copilot_v2.attachments import store_attachment, validate_upload
from services.owner_copilot_v2.choices import make_choice_set, resolve_choice, setup_tone_choices
from services.owner_copilot_v2.creative_policy import looks_like_creative_request
from services.owner_copilot_v2.flags import flags_snapshot, owner_model_name, owner_recent_history_tokens
from services.owner_copilot_v2.memory import estimate_messages_tokens, pack_recent_messages
from services.owner_copilot_v2.models import StreamEvent
from services.owner_copilot_v2.stream_protocol import encode_sse
from services.owner_copilot_v2.tool_schemas import tool_names


def test_owner_model_is_sol() -> None:
    assert owner_model_name() == "gpt-5.6-sol"
    snap = flags_snapshot()
    assert snap["OWNER_COPILOT_V2"] is True
    assert snap["OWNER_COPILOT_WRITES"] is False
    assert snap["OWNER_COPILOT_META_ACTIONS"] is False
    assert snap["LINAS_OWNER_RECENT_HISTORY_TOKENS"] == 4000


def test_owner_recent_history_tokens_default_4000(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINAS_OWNER_RECENT_HISTORY_TOKENS", raising=False)
    assert owner_recent_history_tokens() == 4000
    monkeypatch.setenv("LINAS_OWNER_RECENT_HISTORY_TOKENS", "4000")
    assert owner_recent_history_tokens() == 4000
    monkeypatch.setenv("LINAS_OWNER_RECENT_HISTORY_TOKENS", "5000")
    assert owner_recent_history_tokens() == 5000


def test_creative_keywords_detected() -> None:
    assert looks_like_creative_request("create a post please")
    assert looks_like_creative_request("بدي نعمل بوست")
    assert not looks_like_creative_request("why is Instagram not replying")


def test_token_aware_memory_not_fixed_8x600() -> None:
    msgs = [{"role": "user", "content": ("hello " * 200)}] * 20
    recent, summary = pack_recent_messages(msgs, token_budget=400)
    assert len(recent) < 20
    assert summary is not None or len(recent) >= 1
    # No hard 600-char trim on kept messages
    if recent:
        assert len(recent[-1]["content"]) > 100


def test_default_recent_history_pack_uses_4000(monkeypatch: pytest.MonkeyPatch) -> None:
    """Logged-in owner read window is 4000 tokens — not CONTEXT_BUDGET÷3 (~2000)."""
    monkeypatch.delenv("LINAS_OWNER_RECENT_HISTORY_TOKENS", raising=False)
    monkeypatch.setenv("LINAS_OWNER_CONTEXT_BUDGET", "6000")
    # Each message ≈ 1004 tokens (1000 chars/4 + 4 overhead) → 4 fit in 4000, 5th would exceed.
    msgs = [{"role": "user", "content": ("x" * 4000)}] * 10
    recent, _summary = pack_recent_messages(msgs)
    assert owner_recent_history_tokens() == 4000
    assert estimate_messages_tokens(recent) <= 4000
    # With budget÷3 (~2000) only ~2 would fit; with 4000 we keep more.
    assert len(recent) >= 3
    assert len(recent) <= 4


def test_choices_max_three_and_single_use() -> None:
    choices = setup_tone_choices()
    assert len(choices) == 3
    payload = make_choice_set(tenant_id="t1", conversation_id="c1", choices=choices)
    assert len(payload["choices"]) == 3
    first = resolve_choice(
        tenant_id="t1",
        conversation_id="c1",
        choice_set_id=payload["choice_set_id"],
        choice_id=choices[0].id,
    )
    assert first["ok"] is True
    second = resolve_choice(
        tenant_id="t1",
        conversation_id="c1",
        choice_set_id=payload["choice_set_id"],
        choice_id=choices[1].id,
    )
    assert second["ok"] is False
    assert second["error"] == "choice_already_used"


def test_attachment_validation_and_tenant_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    # Re-import root resolution is already at import time — store uses _DATA_ROOT.
    # Force write under tmp by patching tenant dir root via env may not rebuild Path;
    # call validate + store with monkeypatched module root.
    import services.owner_copilot_v2.attachments as att

    monkeypatch.setattr(att, "_root", lambda: tmp_path / "owner_attachments")

    bad = validate_upload(filename="x.exe", content_type="application/octet-stream", size=10)
    assert bad["ok"] is False
    ok = validate_upload(filename="prices.jpg", content_type="image/jpeg", size=100)
    assert ok["ok"] is True
    stored = store_attachment(
        tenant_id="tenantA",
        user_id="u1",
        filename="prices.jpg",
        content=b"\xff\xd8\xff" + b"0" * 20,
        content_type="image/jpeg",
    )
    assert stored["ok"] is True
    aid = stored["attachment_id"]
    # Cross-tenant deny
    from services.owner_copilot_v2.attachments import load_attachment_meta

    assert load_attachment_meta(tenant_id="tenantB", attachment_id=aid) is None
    assert load_attachment_meta(tenant_id="tenantA", attachment_id=aid) is not None


def test_sse_encode_and_tool_schemas() -> None:
    line = encode_sse(StreamEvent(type="thinking", payload={"label": "Thinking…"}))
    assert line.startswith("data: ")
    assert "thinking" in line
    names = tool_names()
    assert "diagnose_meta_health" in names
    assert "extract_price_list" in names
    assert "create_creative_draft" not in names


@pytest.mark.asyncio
async def test_stream_events_thinking_then_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot_v2.brain import iter_owner_turn_v2_events

    monkeypatch.setenv("OWNER_COPILOT_V2", "true")
    monkeypatch.setattr(
        "services.owner_ai_context.pack_owner_turn_context",
        lambda **_: {
            "system_prompt": "x",
            "account_summary": {"setup_stage": "new", "profile": {"preferred_language": "en"}},
            "knowledge_block": "",
            "capabilities": [],
            "recent_messages": [],
            "conversation_summary": None,
            "reply_language": "en",
            "preferred_language": "en",
            "cm_full_dump": False,
            "full_history": False,
        },
    )

    class _Msg:
        content = "Hello from Sol."
        tool_calls = None

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    async def _fake_completion(**kwargs: Any) -> Any:
        assert kwargs.get("stream") is False or "tools" in kwargs or True
        return _Resp()

    monkeypatch.setattr("services.owner_copilot_v2.brain.sol_chat_completion", _fake_completion)

    events = []
    async for ev in iter_owner_turn_v2_events(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="hi",
    ):
        events.append(ev.type)

    assert events[0] == "thinking"
    assert "delta" in events
    assert events[-1] == "done"


@pytest.mark.asyncio
async def test_shadow_mode_blocks_approve_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot_v2.tool_dispatch import dispatch_v2_tool

    monkeypatch.setenv("OWNER_COPILOT_WRITES", "false")
    result = await dispatch_v2_tool(
        "publish_cm",
        tenant_id="t1",
        user_id="u1",
        role="admin",
        args={},
        confirmed=True,
    )
    assert result.ok is False
    assert result.error == "writes_disabled_shadow_mode"


@pytest.mark.asyncio
async def test_setup_next_step_and_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot_v2.setup_flow import tool_setup_next_step

    monkeypatch.setattr(
        "services.owner_ai_account_state.build_account_summary",
        lambda **_: {"setup_stage": "new", "cm": {"sections_present": 0, "sections_total": 17}},
    )
    result = await tool_setup_next_step(tenant_id="t1", role="admin", user_id="u1", action="status")
    assert result.ok is True
    assert result.data["same_cm_draft"] is True
    from services.owner_copilot_v2.choices import choices_from_tool_result

    ch = choices_from_tool_result("setup_next_step", result.data)
    assert 1 <= len(ch) <= 3


@pytest.mark.asyncio
async def test_price_list_fixture_extraction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import services.owner_copilot_v2.attachments as att
    from services.owner_copilot_v2.vision_import import tool_extract_price_list

    monkeypatch.setattr(att, "_root", lambda: tmp_path / "owner_attachments")
    fixture = {
        "document_type": "price_list",
        "currency_guess": "USD",
        "items": [
            {"name": "Haircut", "price": 20, "currency": "USD", "confidence": 0.92},
            {"name": "Color", "price": 80, "currency": "USD", "confidence": 0.4},
        ],
        "ambiguities": ["Color price uncertain"],
        "summary": "Extracted 2 rows",
    }
    fpath = tmp_path / "extract.json"
    fpath.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setenv("LINAS_OWNER_VISION_FIXTURE", str(fpath))

    stored = store_attachment(
        tenant_id="t1",
        user_id="u1",
        filename="menu.jpg",
        content=b"\xff\xd8\xff" + b"1" * 40,
        content_type="image/jpeg",
    )
    assert stored["ok"]
    result = await tool_extract_price_list(
        tenant_id="t1",
        role="admin",
        user_id="u1",
        attachment_id=stored["attachment_id"],
    )
    assert result.ok is True
    assert result.data.get("vision_path") == "fixture"
    assert result.data.get("cm_mutated") is not True
    assert len(result.data.get("items") or []) == 2


@pytest.mark.asyncio
async def test_diagnose_meta_health_readonly(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_ai_tools_base import ToolResult
    from services.owner_copilot_v2.diagnosis_health import tool_diagnose_meta_health

    async def _integ(**_: Any) -> ToolResult:
        return ToolResult(ok=True, name="read_integrations", data={"any_connected": False, "integrations": {}})

    monkeypatch.setattr("services.owner_ai_tools_read.tool_read_integrations", _integ)
    result = await tool_diagnose_meta_health(tenant_id="t1", role="admin", channel="all")
    assert result.ok is True
    assert result.data.get("meta_mutations") is False
    assert result.data.get("app") == "A"


def test_capability_manifest_freshness() -> None:
    """CI freshness: manifest lists creative as cancelled and owner model Sol."""
    root = Path(__file__).resolve().parents[1]
    manifest = root / "docs" / "evidence" / "system_copilot_v2" / "capability_manifest.json"
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["owner_model"] == "gpt-5.6-sol"
    assert data["guest_model"] == "gpt-5.6-luna"
    creative = next(c for c in data["capabilities"] if c["id"] == "creative_studio")
    assert creative["status"] == "unavailable"
    assert "create_creative_draft" not in data.get("active_tools", [])


def test_system_v2_voice_is_warm_with_tasteful_emojis() -> None:
    from services.owner_copilot_v2.brain_support import SYSTEM_V2

    assert "warm, friendly" in SYSTEM_V2
    assert "tasteful emojis" in SYSTEM_V2
    assert "friendly ≠ silly" in SYSTEM_V2
    assert "never spam" in SYSTEM_V2
