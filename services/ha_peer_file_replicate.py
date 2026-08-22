"""Replicate small tenant-scoped files to the HA peer after a local write."""

from __future__ import annotations

import logging
from pathlib import Path

from services.ha_cm_peer_replicate import (
    HaCmPeerReplicateError,
    _peer_host,
    _run_checked,
    _ssh_target,
    ha_cm_peer_replicate_enabled,
)

_runtime_logger = logging.getLogger("uvicorn.error")
_SSH_OPTIONS = (
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=15",
    "-o",
    "StrictHostKeyChecking=yes",
)


def replicate_file_to_ha_peer(*, local_path: Path, remote_path: str, stage: str) -> None:
    """Best-effort rsync of one file to the peer; no-op when HA peer is not configured."""

    if not ha_cm_peer_replicate_enabled():
        return
    if not local_path.is_file():
        raise HaCmPeerReplicateError(f"HA peer file replicate missing local file stage={stage}")
    command = [
        "rsync",
        "-az",
        "-e",
        " ".join(["ssh", *_SSH_OPTIONS]),
        str(local_path),
        f"{_ssh_target()}:{remote_path}",
    ]
    _run_checked(command, stage=stage)
    _runtime_logger.info("[ha-peer] file_replicated stage=%s peer=%s", stage, _peer_host())
