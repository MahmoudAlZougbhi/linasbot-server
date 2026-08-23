"""Tests for HA CM peer replication after publish."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from services.cm.schemas import PublishedPointer
from services.ha_cm_peer_replicate import (
    HaCmPeerReplicateError,
    _remote_pointer_checksum,
    ha_cm_peer_replicate_enabled,
    replicate_published_cm_to_peer,
    warm_published_cm_peer_cache,
)


def test_ha_cm_peer_replicate_disabled_without_peer_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINAS_HA_PEER_HOST", raising=False)
    assert ha_cm_peer_replicate_enabled() is False
    replicate_published_cm_to_peer(
        tenant_id="linas",
        pointer=PublishedPointer(
            content_version_id="v_testcontent",
            index_version_id="idx_testindex",
            checksums={"actions": "abc"},
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_version="v1",
            embedding_dimensions=1536,
            updated_at="2026-01-01T00:00:00Z",
        ),
    )


def test_ha_cm_peer_replicate_rsyncs_version_index_and_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINAS_HA_PEER_HOST", "10.106.0.4")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))

    tenant = "linas"
    content_id = "v_peer123456"
    index_id = "idx_peer123456"
    cm_root = tmp_path / "tenants" / tenant / "cm"
    content_dir = cm_root / "versions" / content_id / "content"
    content_dir.mkdir(parents=True)
    (content_dir / "actions.json").write_text('{"items":[]}', encoding="utf-8")
    index_dir = cm_root / "indexes" / index_id
    index_dir.mkdir(parents=True)
    (index_dir / "manifest.json").write_text('{"index_id":"idx_peer123456"}', encoding="utf-8")
    pointer_path = cm_root / "published" / "pointer.json"
    pointer_path.parent.mkdir(parents=True)
    pointer_path.write_text(
        '{"content_version_id":"v_peer123456","index_version_id":"idx_peer123456","checksums":{"actions":"x"}}',
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> object:
        calls.append(command)
        if command and command[0] == "ssh":
            return type("R", (), {"returncode": 0, "stdout": "a" * 64, "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with patch("services.ha_cm_peer_replicate.subprocess.run", side_effect=fake_run):
        with patch("services.ha_cm_peer_replicate.compute_checksum", return_value="a" * 64):
            replicate_published_cm_to_peer(
                tenant_id=tenant,
                pointer=PublishedPointer(
                    content_version_id=content_id,
                    index_version_id=index_id,
                    checksums={"actions": "x"},
                    embedding_provider="openai",
                    embedding_model="text-embedding-3-small",
                    embedding_version="v1",
                    embedding_dimensions=1536,
                    updated_at="2026-01-01T00:00:00Z",
                ),
            )

    assert len(calls) == 4
    assert all(call[0] == "rsync" for call in calls[:3])
    assert calls[3][0] == "ssh"


def test_remote_pointer_checksum_uses_string_path_not_posixpath_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINAS_HA_PEER_HOST", "10.106.0.4")
    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str], **kwargs: object) -> object:
        captured["command"] = command
        return type("R", (), {"returncode": 0, "stdout": "a" * 64, "stderr": ""})()

    with patch("services.ha_cm_peer_replicate.subprocess.run", side_effect=fake_run):
        digest = _remote_pointer_checksum("linas")

    assert digest == "a" * 64
    remote_cmd = captured["command"][-1]
    assert "PosixPath" not in remote_cmd
    assert "/pointer.json" in remote_cmd
    assert 'separators=(",",":")' in remote_cmd


def test_warm_published_cm_peer_cache_swallows_peer_error_on_postgres_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINAS_TENANT_RUNTIME_CONFIG_BACKEND", "postgres")
    pointer = PublishedPointer(
        content_version_id="v_testcontent",
        index_version_id="idx_testindex",
        checksums={"actions": "abc"},
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_version="v1",
        embedding_dimensions=1536,
        updated_at="2026-01-01T00:00:00Z",
    )

    with patch(
        "services.ha_cm_peer_replicate.replicate_published_cm_to_peer",
        side_effect=HaCmPeerReplicateError("HA CM peer replicate pointer verify failed"),
    ):
        warm_published_cm_peer_cache(tenant_id="linas", pointer=pointer)


def test_warm_published_cm_peer_cache_reraises_peer_error_on_file_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINAS_TENANT_RUNTIME_CONFIG_BACKEND", "file")
    pointer = PublishedPointer(
        content_version_id="v_testcontent",
        index_version_id="idx_testindex",
        checksums={"actions": "abc"},
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_version="v1",
        embedding_dimensions=1536,
        updated_at="2026-01-01T00:00:00Z",
    )

    with patch(
        "services.ha_cm_peer_replicate.replicate_published_cm_to_peer",
        side_effect=HaCmPeerReplicateError("HA CM peer replicate pointer verify failed"),
    ):
        with pytest.raises(HaCmPeerReplicateError):
            warm_published_cm_peer_cache(tenant_id="linas", pointer=pointer)
