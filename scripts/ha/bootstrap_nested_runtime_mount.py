"""Mount-namespace validation for nested-runtime quarantine."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, NamedTuple

MAX_MOUNTINFO_BYTES = 8 * 1024 * 1024
MOUNTINFO_PATH = Path("/proc/self/mountinfo")


class NestedRuntimeQuarantineError(RuntimeError):
    """Fixed-message failure; member paths and secrets are never echoed."""


class MountContext(NamedTuple):
    namespace_sha256: str


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()


def read_mountinfo_text(path: Path | None = None) -> str:
    source = MOUNTINFO_PATH if path is None else path
    try:
        raw = source.read_bytes()
    except OSError:
        raise NestedRuntimeQuarantineError("nested runtime mount namespace is invalid") from None
    return _validated_mountinfo_text(raw)


def _validated_mountinfo_text(raw: bytes) -> str:
    if not raw or len(raw) > MAX_MOUNTINFO_BYTES:
        raise NestedRuntimeQuarantineError("nested runtime mount namespace is invalid")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise NestedRuntimeQuarantineError("nested runtime mount namespace is invalid") from None


def _unescape_mount_path(raw: str) -> str:
    chars: list[str] = []
    index = 0
    while index < len(raw):
        if raw[index] == "\\" and index + 3 < len(raw) and raw[index + 1 : index + 4].isdigit():
            chars.append(chr(int(raw[index + 1 : index + 4], 8)))
            index += 4
            continue
        chars.append(raw[index])
        index += 1
    return "".join(chars)


def _parse_mountinfo_line(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped:
        return None
    separator = " - "
    if separator not in stripped:
        raise NestedRuntimeQuarantineError("nested runtime mount namespace is invalid")
    left, right = stripped.split(separator, 1)
    left_fields = left.split()
    if len(left_fields) < 5:
        raise NestedRuntimeQuarantineError("nested runtime mount namespace is invalid")
    right_fields = right.split()
    if len(right_fields) < 2:
        raise NestedRuntimeQuarantineError("nested runtime mount namespace is invalid")
    major_text, minor_text = left_fields[2].split(":", 1)
    return {
        "mount_id": int(left_fields[0]),
        "parent_id": int(left_fields[1]),
        "major": int(major_text),
        "minor": int(minor_text),
        "vfs_root": _unescape_mount_path(left_fields[3]),
        "mount_point": _unescape_mount_path(left_fields[4]),
        "filesystem_type": right_fields[0],
        "source": right_fields[1],
    }


def _relative_mount_under_tree(tree_root: Path, mount_point: Path) -> str | None:
    tree = tree_root.resolve()
    candidate = Path(os.path.normpath(str(mount_point)))
    if not candidate.is_absolute():
        return None
    if candidate == tree:
        return "."
    try:
        candidate.relative_to(tree)
    except ValueError:
        return None
    return os.path.relpath(candidate, tree)


def _collect_mount_boundaries(tree_root: Path, mountinfo_text: str) -> list[dict[str, Any]]:
    boundaries: list[dict[str, Any]] = []
    for line in mountinfo_text.splitlines():
        entry = _parse_mountinfo_line(line)
        if entry is None:
            continue
        relative = _relative_mount_under_tree(tree_root, Path(entry["mount_point"]))
        if relative is None:
            continue
        boundaries.append(
            {
                "mount_id": entry["mount_id"],
                "parent_id": entry["parent_id"],
                "major": entry["major"],
                "minor": entry["minor"],
                "vfs_root": entry["vfs_root"],
                "relative": relative,
                "filesystem_type": entry["filesystem_type"],
                "source": entry["source"],
            }
        )
    return sorted(
        boundaries,
        key=lambda item: (
            item["mount_id"],
            item["parent_id"],
            item["major"],
            item["minor"],
            item["vfs_root"],
            item["relative"],
            item["filesystem_type"],
            item["source"],
        ),
    )


def mount_namespace_sha256(boundaries: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical_json(boundaries)).hexdigest()


def prepare_mount_context(tree_root: Path, mountinfo_text: str | None = None) -> MountContext:
    text = (
        _validated_mountinfo_text(mountinfo_text.encode("utf-8"))
        if mountinfo_text is not None
        else read_mountinfo_text()
    )
    boundaries = _collect_mount_boundaries(tree_root, text)
    if boundaries:
        raise NestedRuntimeQuarantineError("nested runtime tree contains a mount point")
    return MountContext(namespace_sha256=mount_namespace_sha256(boundaries))


def verify_mount_context(tree_root: Path, expected_sha256: str, mountinfo_text: str | None = None) -> None:
    context = prepare_mount_context(tree_root, mountinfo_text)
    if context.namespace_sha256 != expected_sha256:
        raise NestedRuntimeQuarantineError("nested runtime mount namespace changed")
