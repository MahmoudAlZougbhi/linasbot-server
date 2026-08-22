"""Detect CM pointer / comment-settings drift between HA nodes."""

from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

from services.cm.atomic_io import compute_checksum, read_json_object
from services.cm.paths import published_pointer_path
from services.cm.constants import DEFAULT_TENANT_ID
from services.durable_event_claim import release_job_lock, try_acquire_job_lock
from services.ha_cm_peer_replicate import _peer_host, _ssh_target, ha_cm_peer_replicate_enabled
from services.meta_comment_reply_settings import _tenant_path

_runtime_logger = logging.getLogger("uvicorn.error")
_SSH_OPTIONS = (
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=15",
    "-o",
    "StrictHostKeyChecking=yes",
)


def _file_checksum(path: Path) -> str | None:
    try:
        payload = read_json_object(path)
    except (OSError, TypeError, ValueError):
        return None
    return compute_checksum(payload)


def _remote_file_checksum(remote_path: str) -> str | None:
    command = [
        "ssh",
        *_SSH_OPTIONS,
        _ssh_target(),
        f"python3 -c \"import json,hashlib; p=json.load(open({remote_path!r})); "
        f"print(hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest())\"",
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    digest = str(completed.stdout or "").strip()
    return digest if len(digest) == 64 else None


async def run_ha_peer_drift_guard_job() -> None:
    if not ha_cm_peer_replicate_enabled():
        return
    if not try_acquire_job_lock("ha_peer_drift_guard_tick", ttl_seconds=240):
        return
    try:
        tenant_id = DEFAULT_TENANT_ID
        pointer = published_pointer_path(tenant_id)
        if pointer.is_file():
            local_digest = _file_checksum(pointer)
            remote_digest = _remote_file_checksum(str(pointer))
            if local_digest and remote_digest and local_digest != remote_digest:
                _runtime_logger.error(
                    "[ha-drift] cm_pointer_mismatch tenant=%s local=%s remote=%s peer=%s",
                    tenant_id,
                    local_digest[:12],
                    remote_digest[:12],
                    _peer_host(),
                )

        comment_settings = _tenant_path(tenant_id)
        if comment_settings.is_file():
            local_digest = hashlib.sha256(comment_settings.read_bytes()).hexdigest()
            remote_digest = _remote_file_checksum(str(comment_settings))
            if remote_digest and local_digest != remote_digest:
                _runtime_logger.error(
                    "[ha-drift] comment_settings_mismatch tenant=%s local=%s remote=%s peer=%s",
                    tenant_id,
                    local_digest[:12],
                    remote_digest[:12],
                    _peer_host(),
                )
    finally:
        release_job_lock("ha_peer_drift_guard_tick")
