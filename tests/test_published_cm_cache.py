"""P1: load_published_content is process-cached per tenant+revision."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.ai_setup import published_cache
from services.ai_setup.version_store import load_published_content
from tests.cm_test_helpers import publish_pointer_content


@pytest.fixture()
def tenant_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    published_cache.invalidate_published_cache()
    published_cache.DISK_LOADS = 0
    return "cache-tenant"


def test_second_load_same_revision_hits_cache(tenant_root: str) -> None:
    publish_pointer_content(tenant_root)
    published_cache.DISK_LOADS = 0
    load_published_content(tenant_root)
    load_published_content(tenant_root)
    assert published_cache.DISK_LOADS == 1


def test_publish_invalidates_cache(tenant_root: str) -> None:
    publish_pointer_content(tenant_root)
    published_cache.DISK_LOADS = 0
    load_published_content(tenant_root)
    publish_pointer_content(tenant_root, {"runtime_limits": {"owner_history_messages": 40}})
    load_published_content(tenant_root)
    assert published_cache.DISK_LOADS == 2
