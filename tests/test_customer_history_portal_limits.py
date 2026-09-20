"""Customer history clip is portal-tunable and defaults to 600 on the customer path."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.brain.history import build_history_snapshot
from tests.cm_test_helpers import publish_pointer_content


@pytest.fixture()
def tenant_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return "cust-hist-tenant"


def test_customer_history_clips_at_600_when_tenant_limits_apply(tenant_root: str) -> None:
    long_text = "c" * 900
    snap = build_history_snapshot(
        [{"id": "m1", "role": "user", "text": long_text}],
        current_inbound_id="m1",
        tenant_id=tenant_root,
    )
    assert len(snap.messages[0].text) == 600
    assert snap.messages[0].text.endswith("…")


def test_customer_history_cap_follows_portal(tenant_root: str) -> None:
    publish_pointer_content(tenant_root, {"runtime_limits": {"customer_history_messages": 10}})
    raw = [{"id": f"m{i}", "role": "user", "text": str(i)} for i in range(30)]
    snap = build_history_snapshot(raw, current_inbound_id="m29", tenant_id=tenant_root)
    assert len(snap.messages) == 10
