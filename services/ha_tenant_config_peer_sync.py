"""Bidirectional HA sync for tenant runtime configuration (CM + integrations)."""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from datetime import UTC
from pathlib import Path
from typing import Any

from services.cm.atomic_io import compute_checksum, read_json_object
from services.cm.paths import draft_dir, indexes_dir, published_pointer_path, tenant_cm_root, versions_dir
from services.cm.schemas import PublishedPointer
from services.cm.version_store import read_published_pointer
from services.ha_cm_peer_replicate import (
    HaCmPeerReplicateError,
    _peer_host,
    _rsync_dir,
    _run_checked,
    _ssh_target,
    ha_cm_peer_replicate_enabled,
    replicate_published_cm_to_peer,
)
from services.meta_comment_reply_settings import _tenant_path as comment_settings_path

_runtime_logger = logging.getLogger("uvicorn.error")
_SSH_OPTIONS = (
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=15",
    "-o",
    "StrictHostKeyChecking=yes",
)
_RSYNC_TIMEOUT_SECONDS = 120


def _data_root() -> Path:
    from storage.persistent_storage import get_data_root

    return Path(get_data_root())


def _rsync_peer_dir_to_local(*, remote_dir: str, local_dir: Path, stage: str) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "rsync",
        "-az",
        "-e",
        " ".join(["ssh", *_SSH_OPTIONS]),
        f"{_ssh_target()}:{remote_dir}/",
        f"{local_dir}/",
    ]
    _run_checked(command, stage=stage)


def _rsync_local_file_to_peer(*, local_path: Path, remote_path: str, stage: str) -> None:
    if not local_path.is_file():
        raise HaCmPeerReplicateError(f"HA tenant sync missing local file stage={stage}")
    command = [
        "rsync",
        "-az",
        "-e",
        " ".join(["ssh", *_SSH_OPTIONS]),
        str(local_path),
        f"{_ssh_target()}:{remote_path}",
    ]
    _run_checked(command, stage=stage)


def _rsync_peer_file_to_local(*, remote_path: str, local_path: Path, stage: str) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "rsync",
        "-az",
        "-e",
        " ".join(["ssh", *_SSH_OPTIONS]),
        f"{_ssh_target()}:{remote_path}",
        str(local_path),
    ]
    _run_checked(command, stage=stage)


def _remote_json(path: str) -> dict[str, Any] | None:
    command = [
        "ssh",
        *_SSH_OPTIONS,
        _ssh_target(),
        f"python3 -c \"import json; print(json.dumps(json.load(open({path!r}))))\"",
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(str(completed.stdout or "").strip())
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _pointer_digest(tenant_id: str) -> str | None:
    path = published_pointer_path(tenant_id)
    if not path.is_file():
        return None
    try:
        return compute_checksum(read_json_object(path))
    except (OSError, TypeError, ValueError):
        return None


def _comment_settings_digest(tenant_id: str) -> str | None:
    path = comment_settings_path(tenant_id)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _comment_settings_updated_at(tenant_id: str) -> float:
    path = comment_settings_path(tenant_id)
    if not path.is_file():
        return 0.0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return path.stat().st_mtime
    settings = payload.get("settings") if isinstance(payload, dict) else None
    if not isinstance(settings, dict):
        return path.stat().st_mtime
    latest = 0.0
    for raw in settings.values():
        if isinstance(raw, dict):
            latest = max(latest, float(raw.get("updated_at") or 0.0))
    return latest or path.stat().st_mtime


def _remote_comment_settings_updated_at(tenant_id: str) -> float:
    remote_path = str(comment_settings_path(tenant_id))
    payload = _remote_json(remote_path)
    if not isinstance(payload, dict):
        return 0.0
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        return 0.0
    latest = 0.0
    for raw in settings.values():
        if isinstance(raw, dict):
            latest = max(latest, float(raw.get("updated_at") or 0.0))
    return latest


def replicate_cm_draft_to_peer(tenant_id: str) -> None:
    if not ha_cm_peer_replicate_enabled():
        return
    local_draft = draft_dir(tenant_id)
    if not local_draft.is_dir():
        return
    remote_draft = f"{tenant_cm_root(tenant_id)}/draft"
    _rsync_dir(local_dir=local_draft, remote_dir=remote_draft, stage="cm_draft_push")
    _runtime_logger.info("[ha-sync] cm_draft_pushed tenant=%s peer=%s", tenant_id, _peer_host())


def replicate_comment_settings_to_peer(tenant_id: str) -> None:
    if not ha_cm_peer_replicate_enabled():
        return
    local_path = comment_settings_path(tenant_id)
    if not local_path.is_file():
        return
    _rsync_local_file_to_peer(
        local_path=local_path,
        remote_path=str(local_path),
        stage="comment_settings_push",
    )
    _runtime_logger.info("[ha-sync] comment_settings_pushed tenant=%s peer=%s", tenant_id, _peer_host())


def _pull_published_cm_from_peer(tenant_id: str, pointer: PublishedPointer) -> None:
    content_version_id = str(pointer.content_version_id or "").strip()
    index_version_id = str(pointer.index_version_id or "").strip()
    if not content_version_id or not index_version_id:
        raise HaCmPeerReplicateError("HA tenant sync pull requires content and index version ids")
    remote_root = f"{_data_root()}/tenants/{tenant_id}/cm"
    _rsync_peer_dir_to_local(
        remote_dir=f"{remote_root}/versions/{content_version_id}",
        local_dir=versions_dir(tenant_id) / content_version_id,
        stage="cm_content_pull",
    )
    _rsync_peer_dir_to_local(
        remote_dir=f"{remote_root}/indexes/{index_version_id}",
        local_dir=indexes_dir(tenant_id) / index_version_id,
        stage="cm_index_pull",
    )
    _rsync_peer_dir_to_local(
        remote_dir=f"{remote_root}/published",
        local_dir=published_pointer_path(tenant_id).parent,
        stage="cm_pointer_pull",
    )
    from services.customer_reply_v2.manifest import clear_manifest_cache

    clear_manifest_cache(tenant_id)


def _reconcile_published_cm(tenant_id: str) -> str:
    local_pointer = read_published_pointer(tenant_id)
    remote_payload = _remote_json(str(published_pointer_path(tenant_id)))
    if local_pointer is None and remote_payload is None:
        return "cm_published=absent"
    if local_pointer is None and remote_payload is not None:
        _pull_published_cm_from_peer(tenant_id, PublishedPointer.model_validate(remote_payload))
        return "cm_published=pulled"
    if local_pointer is not None and remote_payload is None:
        replicate_published_cm_to_peer(tenant_id=tenant_id, pointer=local_pointer)
        return "cm_published=pushed"
    assert local_pointer is not None
    remote_pointer = PublishedPointer.model_validate(remote_payload)
    local_digest = _pointer_digest(tenant_id)
    remote_digest = compute_checksum(remote_payload)
    if local_digest and local_digest == remote_digest:
        return "cm_published=matched"
    local_ts = local_pointer.updated_at.astimezone(UTC).timestamp()
    remote_ts = remote_pointer.updated_at.astimezone(UTC).timestamp()
    if local_ts >= remote_ts:
        replicate_published_cm_to_peer(tenant_id=tenant_id, pointer=local_pointer)
        return "cm_published=pushed"
    _pull_published_cm_from_peer(tenant_id, remote_pointer)
    return "cm_published=pulled"


def _reconcile_comment_settings(tenant_id: str) -> str:
    local_digest = _comment_settings_digest(tenant_id)
    remote_payload = _remote_json(str(comment_settings_path(tenant_id)))
    remote_digest = None
    if isinstance(remote_payload, dict):
        remote_digest = hashlib.sha256(
            json.dumps(remote_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    if local_digest is None and remote_digest is None:
        return "comment_settings=absent"
    if local_digest is None and remote_digest is not None:
        _rsync_peer_file_to_local(
            remote_path=str(comment_settings_path(tenant_id)),
            local_path=comment_settings_path(tenant_id),
            stage="comment_settings_pull",
        )
        return "comment_settings=pulled"
    if local_digest is not None and remote_digest is None:
        replicate_comment_settings_to_peer(tenant_id)
        return "comment_settings=pushed"
    assert local_digest is not None and remote_digest is not None
    if local_digest == remote_digest:
        return "comment_settings=matched"
    if _comment_settings_updated_at(tenant_id) >= _remote_comment_settings_updated_at(tenant_id):
        replicate_comment_settings_to_peer(tenant_id)
        return "comment_settings=pushed"
    _rsync_peer_file_to_local(
        remote_path=str(comment_settings_path(tenant_id)),
        local_path=comment_settings_path(tenant_id),
        stage="comment_settings_pull",
    )
    return "comment_settings=pulled"


def _reconcile_cm_drafts(tenant_id: str) -> str:
    local_draft = draft_dir(tenant_id)
    remote_draft = f"{tenant_cm_root(tenant_id)}/draft"
    if local_draft.is_dir():
        _rsync_dir(local_dir=local_draft, remote_dir=remote_draft, stage="cm_draft_push")
    _rsync_peer_dir_to_local(remote_dir=remote_draft, local_dir=local_draft, stage="cm_draft_pull")
    return "cm_draft=merged"


def reconcile_tenant_config_with_peer(tenant_id: str) -> dict[str, str]:
    """Repair tenant runtime config by syncing newer state to the peer (never blocks deploy)."""

    if not ha_cm_peer_replicate_enabled():
        return {"status": "disabled"}
    results = {
        "cm_published": _reconcile_published_cm(tenant_id),
        "cm_draft": _reconcile_cm_drafts(tenant_id),
        "comment_settings": _reconcile_comment_settings(tenant_id),
        "peer": _peer_host(),
    }
    _runtime_logger.info(
        "[ha-sync] tenant=%s cm=%s draft=%s comments=%s peer=%s",
        tenant_id,
        results["cm_published"],
        results["cm_draft"],
        results["comment_settings"],
        results["peer"],
    )
    return results
