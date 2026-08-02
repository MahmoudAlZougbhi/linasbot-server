"""CM draft storage concurrency and publish gate."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("CM_PUBLISH_ENABLED", "false")

from services.cm.publish_gate import PublishDisabledError, ensure_publish_enabled
from services.cm.storage import ConflictError, ensure_defaults, get_draft, put_draft


@pytest.fixture()
def tenant_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return tmp_path


def test_draft_put_get_roundtrip(tenant_root: Path) -> None:
    ensure_defaults(tenant_id="tenant_a")
    env = get_draft("ai_basics", tenant_id="tenant_a")
    assert env.revision >= 0
    etag = env.etag
    updated = put_draft(
        "ai_basics",
        payload={**env.payload, "ai_display_name": "Marwa"},
        if_match=etag,
        tenant_id="tenant_a",
        updated_by="tester",
    )
    assert updated.payload["ai_display_name"] == "Marwa"
    assert updated.revision == env.revision + 1
    with pytest.raises(ConflictError):
        put_draft(
            "ai_basics",
            payload=updated.payload,
            if_match=etag,
            tenant_id="tenant_a",
            updated_by="tester",
        )


def test_publish_disabled() -> None:
    with pytest.raises(PublishDisabledError):
        ensure_publish_enabled()
