"""Replicate published CM artifacts to the HA peer after a local pointer flip."""

from __future__ import annotations

import ipaddress
import logging
import os
import subprocess
from pathlib import Path

from services.cm.atomic_io import compute_checksum, read_json_object
from services.cm.paths import indexes_dir, published_pointer_path, versions_dir
from services.cm.schemas import PublishedPointer

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


class HaCmPeerReplicateError(RuntimeError):
    """Raised when the peer could not be brought to the same published CM state."""


def _peer_host() -> str:
    return str(os.getenv("LINAS_HA_PEER_HOST") or "").strip()


def ha_cm_peer_replicate_enabled() -> bool:
    host = _peer_host()
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _ssh_target() -> str:
    host = _peer_host()
    if not host:
        raise HaCmPeerReplicateError("HA peer host is not configured")
    return f"root@{host}"


def _data_root() -> Path:
    from storage.persistent_storage import get_data_root

    return Path(get_data_root())


def _run_checked(command: list[str], *, stage: str) -> None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=_RSYNC_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HaCmPeerReplicateError(f"HA CM peer replicate failed stage={stage}") from exc
    if completed.returncode != 0:
        raise HaCmPeerReplicateError(f"HA CM peer replicate failed stage={stage}")


def _rsync_dir(*, local_dir: Path, remote_dir: str, stage: str) -> None:
    if not local_dir.is_dir():
        raise HaCmPeerReplicateError(f"HA CM peer replicate missing local dir stage={stage}")
    command = [
        "rsync",
        "-az",
        "-e",
        " ".join(["ssh", *_SSH_OPTIONS]),
        f"{local_dir}/",
        f"{_ssh_target()}:{remote_dir}/",
    ]
    _run_checked(command, stage=stage)


def _remote_pointer_checksum(tenant_id: str) -> str:
    remote_path = published_pointer_path(tenant_id)
    command = [
        "ssh",
        *_SSH_OPTIONS,
        _ssh_target(),
        f"python3 -c \"import json,hashlib; p=json.load(open({remote_path!r})); "
        f"print(hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest())\"",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HaCmPeerReplicateError("HA CM peer replicate pointer verify failed") from exc
    if completed.returncode != 0:
        raise HaCmPeerReplicateError("HA CM peer replicate pointer verify failed")
    digest = str(completed.stdout or "").strip()
    if len(digest) != 64:
        raise HaCmPeerReplicateError("HA CM peer replicate pointer verify returned invalid digest")
    return digest


def replicate_published_cm_to_peer(
    *,
    tenant_id: str,
    pointer: PublishedPointer | dict[str, object],
) -> None:
    """Copy the published version/index trees and pointer to the HA peer (fail closed)."""

    if not ha_cm_peer_replicate_enabled():
        return

    resolved = pointer if isinstance(pointer, PublishedPointer) else PublishedPointer.model_validate(pointer)
    tid = str(tenant_id or "").strip()
    if not tid:
        raise HaCmPeerReplicateError("HA CM peer replicate requires tenant_id")

    content_version_id = str(resolved.content_version_id or "").strip()
    index_version_id = str(resolved.index_version_id or "").strip()
    if not content_version_id or not index_version_id:
        raise HaCmPeerReplicateError("HA CM peer replicate requires content and index version ids")

    local_content = versions_dir(tid) / content_version_id
    local_index = indexes_dir(tid) / index_version_id
    local_pointer = published_pointer_path(tid)
    if not local_pointer.is_file():
        raise HaCmPeerReplicateError("HA CM peer replicate local pointer is missing")

    remote_root = f"{_data_root()}/tenants/{tid}/cm"
    _rsync_dir(
        local_dir=local_content,
        remote_dir=f"{remote_root}/versions/{content_version_id}",
        stage="content_version",
    )
    _rsync_dir(
        local_dir=local_index,
        remote_dir=f"{remote_root}/indexes/{index_version_id}",
        stage="index_version",
    )
    _rsync_dir(
        local_dir=local_pointer.parent,
        remote_dir=f"{remote_root}/published",
        stage="pointer",
    )

    local_payload = read_json_object(local_pointer)
    local_digest = compute_checksum(local_payload)
    remote_digest = _remote_pointer_checksum(tid)
    if local_digest != remote_digest:
        raise HaCmPeerReplicateError("HA CM peer replicate pointer checksum mismatch after rsync")

    _runtime_logger.info(
        "[ha-cm] peer_replicated tenant=%s content=%s index=%s peer=%s",
        tid,
        content_version_id,
        index_version_id,
        _peer_host(),
    )
