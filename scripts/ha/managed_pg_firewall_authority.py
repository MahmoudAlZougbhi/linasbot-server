"""Root/operator-owned local authority primitives for Managed PG firewall plans."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import os
import re
import shutil
import stat
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class FirewallContractError(RuntimeError):
    """Fixed-message failure; provider output and credentials are never echoed."""


_MAX_AUTHORITY_BYTES = 1 << 20
_LOCK_NAME = ".managed-pg-firewall.lock"
_RECEIPT_NAME_RE = re.compile(r"managed-pg-firewall-mpf_[0-9a-f]{64}\.(?:intent|complete|superseded)\.json")
_RECEIPT_TEMP_NAME_RE = re.compile(
    r"\.managed-pg-firewall-mpf_[0-9a-f]{64}\.(?:intent|complete|superseded)\.json\.writing"
)
_QUARANTINE_NAME_RE = re.compile(r"\.managed-pg-firewall-quarantine-[0-9a-f]{16}-[0-9a-f]{64}\.json")


def timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")  # noqa: UP017


def parse_time(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise FirewallContractError("firewall authority time is invalid")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FirewallContractError("firewall authority time is invalid") from exc
    if value.tzinfo is None:
        raise FirewallContractError("firewall authority time is invalid")
    return value.astimezone(timezone.utc)  # noqa: UP017


def canonical(value: object) -> bytes:
    import json

    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_rules(
    raw: object,
    *,
    cluster_id: str,
    allowed_types: Collection[str],
    allowed_keys: Collection[str],
) -> list[dict[str, str]]:
    rows: object = raw
    if isinstance(raw, dict):
        if set(raw) != {"rules"}:
            raise FirewallContractError("provider firewall response schema is invalid")
        rows = raw["rules"]
    if not isinstance(rows, list):
        raise FirewallContractError("provider firewall rules are invalid")
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict) or not {"type", "value"}.issubset(row) or not set(row).issubset(allowed_keys):
            raise FirewallContractError("provider firewall rule schema is invalid")
        rule_type = row.get("type")
        value = row.get("value")
        if not isinstance(rule_type, str) or rule_type not in allowed_types:
            raise FirewallContractError("provider firewall rule type is invalid")
        if (
            not isinstance(value, str)
            or not value
            or len(value.encode("utf-8")) > 255
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise FirewallContractError("provider firewall rule value is invalid")
        cluster = row.get("cluster_uuid")
        if cluster is not None and cluster != cluster_id:
            raise FirewallContractError("provider firewall rule targets another cluster")
        description = row.get("description")
        if description is not None and (
            not isinstance(description, str)
            or len(description.encode("utf-8")) > 1_000
            or any(ord(character) < 32 or ord(character) == 127 for character in description)
        ):
            raise FirewallContractError("provider firewall rule description is invalid")
        identity = (rule_type, value)
        if identity in seen:
            raise FirewallContractError("provider firewall rules contain a duplicate")
        seen.add(identity)
        normalized_rule = {"type": rule_type, "value": value}
        if description is not None:
            normalized_rule["description"] = description
        normalized.append(normalized_rule)
    return sorted(normalized, key=lambda item: (item["type"], item["value"]))


def secure_executable(raw: str | None, *, default_name: str) -> tuple[Path, str]:
    selected = raw or shutil.which(default_name)
    if not selected:
        raise FirewallContractError(f"{default_name} is unavailable")
    path = Path(selected).expanduser().resolve(strict=True)
    info = path.stat()
    if (
        not path.is_absolute()
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(info.st_mode) & 0o022
        or not os.access(path, os.X_OK)
    ):
        raise FirewallContractError(f"{default_name} executable authority is unsafe")
    return path, sha256(path.read_bytes())


def _is_transaction_authority_name(name: str) -> bool:
    normalized = name.casefold()
    return (
        normalized == _LOCK_NAME
        or _RECEIPT_NAME_RE.fullmatch(normalized) is not None
        or _RECEIPT_TEMP_NAME_RE.fullmatch(normalized) is not None
        or _QUARANTINE_NAME_RE.fullmatch(normalized) is not None
    )


def secure_parent(path: Path, *, allow_transaction_authority: bool = False) -> Path:
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise FirewallContractError("firewall authority path must be absolute")
    if not allow_transaction_authority and _is_transaction_authority_name(path.name):
        raise FirewallContractError("firewall artifact path uses a reserved transaction namespace")
    parent = path.parent
    if parent.resolve(strict=True) != parent:
        raise FirewallContractError("firewall authority directory is not canonical")
    info = parent.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_gid != os.getegid()
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        raise FirewallContractError("firewall authority directory is unsafe")
    return parent


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def artifact_lock(parent: Path) -> Iterator[None]:
    lock = parent / ".managed-pg-firewall.lock"
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
            or info.st_gid != os.getegid()
            or info.st_nlink != 1
        ):
            raise FirewallContractError("firewall authority lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def secure_read(path: Path, *, allow_transaction_authority: bool = False) -> bytes:
    parent = secure_parent(path, allow_transaction_authority=allow_transaction_authority)
    info = path.lstat()
    temporary = parent / f".{path.name}.writing"
    if info.st_nlink == 2 and temporary.exists() and not temporary.is_symlink():
        temp_info = temporary.lstat()
        if (
            temp_info.st_ino == info.st_ino
            and temp_info.st_dev == info.st_dev
            and stat.S_ISREG(temp_info.st_mode)
            and stat.S_IMODE(temp_info.st_mode) == 0o600
            and temp_info.st_uid == os.geteuid()
            and temp_info.st_gid == os.getegid()
        ):
            temporary.unlink()
            _fsync_dir(parent)
            info = path.lstat()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
            or info.st_gid != os.getegid()
            or info.st_nlink != 1
        ):
            raise FirewallContractError("firewall authority file is unsafe")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read(_MAX_AUTHORITY_BYTES + 1)
        if len(payload) > _MAX_AUTHORITY_BYTES:
            raise FirewallContractError("firewall authority file is too large")
        return payload
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_temporary(path: Path) -> tuple[bytes, os.stat_result]:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
            or info.st_gid != os.getegid()
            or info.st_nlink != 1
        ):
            raise FirewallContractError("firewall authority temporary is unsafe")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read(_MAX_AUTHORITY_BYTES + 1)
        if len(payload) > _MAX_AUTHORITY_BYTES:
            raise FirewallContractError("firewall authority temporary is too large")
        return payload, info
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _unlink_same_file(path: Path, expected: os.stat_result) -> None:
    current = path.lstat()
    if current.st_dev != expected.st_dev or current.st_ino != expected.st_ino:
        raise FirewallContractError("firewall authority temporary changed")
    path.unlink()


def _write_quarantine(path: Path, payload: bytes) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        if not hmac.compare_digest(
            secure_read(path, allow_transaction_authority=True),
            payload,
        ):
            raise FirewallContractError("firewall authority quarantine already differs") from None
        return
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_dir(path.parent)
        if not hmac.compare_digest(
            secure_read(path, allow_transaction_authority=True),
            payload,
        ):
            raise FirewallContractError("firewall authority quarantine readback differs")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _quarantine_temporary(parent: Path, temporary: Path, payload: bytes, info: os.stat_result) -> None:
    name_digest = sha256(temporary.name.encode("utf-8"))[:16]
    quarantine = parent / f".managed-pg-firewall-quarantine-{name_digest}-{sha256(payload)}.json"
    _write_quarantine(quarantine, payload)
    current_payload, current_info = _read_temporary(temporary)
    if not hmac.compare_digest(current_payload, payload):
        raise FirewallContractError("firewall authority temporary changed during quarantine")
    if current_info.st_dev != info.st_dev or current_info.st_ino != info.st_ino:
        raise FirewallContractError("firewall authority temporary changed during quarantine")
    _unlink_same_file(temporary, info)
    _fsync_dir(parent)
    raise FirewallContractError("firewall authority temporary differed and was quarantined")


def write_once(
    path: Path,
    payload: bytes,
    *,
    allow_transaction_authority: bool = False,
) -> None:
    parent = secure_parent(path, allow_transaction_authority=allow_transaction_authority)
    temporary = parent / f".{path.name}.writing"
    if path.exists() or path.is_symlink():
        if not hmac.compare_digest(
            secure_read(path, allow_transaction_authority=allow_transaction_authority),
            payload,
        ):
            raise FirewallContractError("firewall authority file already differs")
        if temporary.exists() and not temporary.is_symlink():
            temp_payload, temp_info = _read_temporary(temporary)
            if not hmac.compare_digest(temp_payload, payload):
                _quarantine_temporary(parent, temporary, temp_payload, temp_info)
            _unlink_same_file(temporary, temp_info)
            _fsync_dir(parent)
        return
    if temporary.exists() or temporary.is_symlink():
        temp_payload, temp_info = _read_temporary(temporary)
        if hmac.compare_digest(temp_payload, payload):
            os.link(temporary, path)
            _fsync_dir(parent)
            _unlink_same_file(temporary, temp_info)
            _fsync_dir(parent)
            if not hmac.compare_digest(
                secure_read(path, allow_transaction_authority=allow_transaction_authority),
                payload,
            ):
                raise FirewallContractError("firewall authority readback differs")
            return
        _quarantine_temporary(parent, temporary, temp_payload, temp_info)
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        _fsync_dir(parent)
        temporary.unlink()
        _fsync_dir(parent)
        if not hmac.compare_digest(
            secure_read(path, allow_transaction_authority=allow_transaction_authority),
            payload,
        ):
            raise FirewallContractError("firewall authority readback differs")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
