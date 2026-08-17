"""CM unpublish clears the Live pointer so customer AI stops."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.cm.schemas import PublishedPointer
from services.cm.version_store import (
    clear_published_pointer,
    read_published_pointer,
    write_published_pointer,
)


@pytest.fixture()
def tenant_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return tmp_path


def test_clear_published_pointer_turns_live_off(tenant_root: Path) -> None:
    del tenant_root
    tid = "unpublish-tenant"
    assert read_published_pointer(tid) is None
    assert clear_published_pointer(tid) is False

    write_published_pointer(
        tid,
        PublishedPointer(
            content_version_id="cv1",
            index_version_id="ix1",
            checksums={"ai_basics": "abc"},
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_version="v1",
            embedding_dimensions=1536,
        ),
    )
    assert read_published_pointer(tid) is not None
    assert clear_published_pointer(tid) is True
    assert read_published_pointer(tid) is None
    assert clear_published_pointer(tid) is False
