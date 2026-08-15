"""Root-owned, canonical, atomic compare-and-swap environment updates."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from scripts.ha.production_mutation_guard import (
    LOCK_PATH,
    _require_inherited_lock,
    require_mutation_context_from_environment,
)

CANONICAL_ENV_PATH = Path("/opt/linasbot/.env")
ENV_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*")


def _secure_snapshot(path: Path, *, owner_uid: int, owner_gid: int) -> tuple[bytes, os.stat_result]:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        current = os.fstat(descriptor)
        if (
            not stat.S_ISREG(current.st_mode)
            or stat.S_IMODE(current.st_mode) != 0o600
            or current.st_uid != owner_uid
            or current.st_gid != owner_gid
        ):
            raise RuntimeError("Canonical production environment security contract is invalid")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read()
        return payload, current
    finally:
        os.close(descriptor)


def _normalize(updates: Mapping[str, str], remove_keys: frozenset[str]) -> tuple[dict[str, str], frozenset[str]]:
    normalized: dict[str, str] = {}
    for raw_key, raw_value in updates.items():
        key = str(raw_key).strip()
        value = str(raw_value)
        if ENV_KEY_RE.fullmatch(key) is None or any(char in value for char in ("\n", "\r", "\0")):
            raise RuntimeError("Environment mutation contains an invalid entry")
        normalized[key] = value
    removed = frozenset(str(value).strip() for value in remove_keys)
    if any(ENV_KEY_RE.fullmatch(key) is None for key in removed):
        raise RuntimeError("Environment mutation contains an invalid removal")
    if removed & normalized.keys():
        raise RuntimeError("Environment key cannot be updated and removed together")
    return normalized, removed


def _render(original: bytes, updates: Mapping[str, str], remove_keys: frozenset[str]) -> bytes:
    try:
        text = original.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Canonical production environment is not UTF-8") from exc
    output: list[str] = []
    written: set[str] = set()
    for line in text.splitlines():
        key = ""
        if "=" in line and not line.lstrip().startswith("#"):
            candidate = line.split("=", 1)[0].strip()
            if ENV_KEY_RE.fullmatch(candidate):
                key = candidate
        if key in remove_keys:
            continue
        if key in updates:
            if key not in written:
                output.append(f"{key}={updates[key]}")
                written.add(key)
            continue
        output.append(line)
    for key in sorted(updates):
        if key not in written:
            output.append(f"{key}={updates[key]}")
    return ("\n".join(output) + "\n").encode("utf-8")


def atomic_update_env_cas(
    path: Path,
    updates: Mapping[str, str],
    *,
    lock_fd: int,
    lock_path: Path,
    remove_keys: frozenset[str] = frozenset(),
    owner_uid: int = 0,
    owner_gid: int = 0,
    before_compare: Callable[[], None] | None = None,
) -> None:
    """Replace selected values under the inherited common mutation lock."""

    _require_inherited_lock(lock_fd, lock_path)
    normalized, removed = _normalize(updates, remove_keys)
    original, original_stat = _secure_snapshot(path, owner_uid=owner_uid, owner_gid=owner_gid)
    replacement = _render(original, normalized, removed)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.prod-mutation.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.chown(temporary, owner_uid, owner_gid)
        if before_compare is not None:
            before_compare()
        current, current_stat = _secure_snapshot(path, owner_uid=owner_uid, owner_gid=owner_gid)
        identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(original_stat, field) != getattr(current_stat, field) for field in identity) or not (
            hashlib.sha256(original).digest() == hashlib.sha256(current).digest()
        ):
            raise RuntimeError("Canonical production environment changed during mutation")
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        persisted, _ = _secure_snapshot(path, owner_uid=owner_uid, owner_gid=owner_gid)
        if persisted != replacement:
            raise RuntimeError("Canonical production environment verification failed")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def atomic_update_canonical_env(updates: Mapping[str, str], *, remove_keys: frozenset[str] = frozenset()) -> None:
    if os.geteuid() != 0 or os.getegid() != 0:
        raise RuntimeError("Canonical production environment mutation requires root")
    script = os.environ.get("LINAS_PRODUCTION_MUTATION_SCRIPT") or os.environ.get("LINAS_DEPLOY_MUTATION_SCRIPT", "")
    lock_fd = require_mutation_context_from_environment(script)
    atomic_update_env_cas(
        CANONICAL_ENV_PATH,
        updates,
        lock_fd=lock_fd,
        lock_path=LOCK_PATH,
        remove_keys=remove_keys,
    )
