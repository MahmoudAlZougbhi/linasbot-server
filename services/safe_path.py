"""Canonical path containment helpers for backup/restore/upload paths."""

from __future__ import annotations

import os
import re
from pathlib import Path

_UNSAFE_NAME = re.compile(r"[\x00]|[/\\]|\.\.")


def is_safe_relative_name(name: str) -> bool:
    """Return True if name is a single relative segment with no traversal."""
    if not name or not isinstance(name, str):
        return False
    if name in {".", ".."}:
        return False
    if _UNSAFE_NAME.search(name):
        return False
    if os.path.isabs(name):
        return False
    # Reject URL-encoded traversal remnants after a single decode layer
    lowered = name.lower()
    if "%2e" in lowered or "%2f" in lowered or "%5c" in lowered:
        return False
    return True


def resolve_under_root(root: str | Path, *parts: str) -> Path:
    """
    Join parts under root and resolve. Raise ValueError if result escapes root.
    """
    root_path = Path(root).resolve()
    candidate = root_path.joinpath(*parts).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("Path escapes allowed root") from exc
    return candidate


def resolve_backup_filename(root: str | Path, filename: str, *, required_prefix: str | None = None) -> Path:
    """
    Resolve a server-listed backup filename under root.
    Only plain basenames are accepted; optional prefix filter for known backups.
    """
    if not is_safe_relative_name(filename):
        raise ValueError("Invalid backup filename")
    base = os.path.basename(filename)
    if base != filename:
        raise ValueError("Invalid backup filename")
    if required_prefix and not base.startswith(required_prefix):
        raise ValueError("Backup filename does not match expected pattern")
    return resolve_under_root(root, base)
