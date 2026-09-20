"""Sol packs last 100 owner messages; no 600-char clip on owner path."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.owner_copilot.context import pack_owner_turn_context
from services.runtime_limits.window import window_owner_messages
from tests.cm_test_helpers import publish_pointer_content


@pytest.fixture()
def tenant_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return "sol-hist-tenant"


def test_window_keeps_last_100_of_120() -> None:
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(120)]
    packed = window_owner_messages(msgs, n=100, max_chars=0)
    assert len(packed) == 100
    assert packed[0]["content"] == "m20"
    assert packed[-1]["content"] == "m119"


def test_owner_pack_no_600_char_trim(tenant_root: str) -> None:
    long_text = "L" * 900
    msgs = [{"role": "user", "content": f"n{i}"} for i in range(119)] + [{"role": "user", "content": long_text}]
    ctx = pack_owner_turn_context(
        tenant_id=tenant_root,
        user_id="u1",
        user_text=long_text,
        messages=msgs,
    )
    recent = ctx["recent_messages"]
    assert len(recent) == 100
    assert recent[-1]["content"] == long_text
    assert "…" not in recent[-1]["content"]


def test_portal_override_history_n(tenant_root: str) -> None:
    publish_pointer_content(tenant_root, {"runtime_limits": {"owner_history_messages": 12}})
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(30)]
    ctx = pack_owner_turn_context(tenant_id=tenant_root, user_id="u1", user_text="hi", messages=msgs)
    assert len(ctx["recent_messages"]) == 12
    assert ctx["owner_history_messages"] == 12
