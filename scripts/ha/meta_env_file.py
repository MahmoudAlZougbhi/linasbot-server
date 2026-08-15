"""Crash-safe updates for the canonical production environment file."""

from __future__ import annotations

import os
import re
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path

ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def require_secure_env_file(path: Path) -> os.stat_result:
    """Require a non-symlink 0600 file owned by the invoking service account."""

    try:
        current = path.lstat()
    except OSError as exc:
        raise RuntimeError("Canonical production environment is unavailable") from exc
    if (
        not stat.S_ISREG(current.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or stat.S_IMODE(current.st_mode) != 0o600
        or current.st_uid != os.geteuid()
        or current.st_gid != os.getegid()
    ):
        raise RuntimeError("Canonical production environment security contract is invalid")
    return current


def atomic_update_env(
    path: Path,
    updates: Mapping[str, str],
    *,
    remove_keys: frozenset[str] = frozenset(),
) -> None:
    """Replace selected keys once, preserving unrelated lines and file ownership."""

    original_stat = require_secure_env_file(path)
    normalized_updates: dict[str, str] = {}
    for raw_key, raw_value in updates.items():
        key = str(raw_key).strip()
        value = str(raw_value)
        if not ENV_KEY_RE.fullmatch(key) or any(char in value for char in ("\n", "\r", "\0")):
            raise RuntimeError("Environment update contains an invalid entry")
        normalized_updates[key] = value
    normalized_remove = {str(key).strip() for key in remove_keys}
    if any(not ENV_KEY_RE.fullmatch(key) for key in normalized_remove):
        raise RuntimeError("Environment removal contains an invalid key")
    if normalized_remove & normalized_updates.keys():
        raise RuntimeError("Environment key cannot be updated and removed together")

    output: list[str] = []
    written: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        key = ""
        if "=" in line and not line.lstrip().startswith("#"):
            candidate = line.split("=", 1)[0].strip()
            if ENV_KEY_RE.fullmatch(candidate):
                key = candidate
        if key in normalized_remove:
            continue
        if key in normalized_updates:
            if key not in written:
                output.append(f"{key}={normalized_updates[key]}")
                written.add(key)
            continue
        output.append(line)
    for key in sorted(normalized_updates):
        if key not in written:
            output.append(f"{key}={normalized_updates[key]}")

    fd, raw_temporary = tempfile.mkstemp(prefix=".env.meta-stage.", dir=path.parent)
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(output) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.chown(temporary, original_stat.st_uid, original_stat.st_gid)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
