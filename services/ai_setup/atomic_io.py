"""Atomic filesystem helpers for CM draft/published storage."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def compute_checksum(value: object) -> str:
    """SHA-256 of canonical JSON (sorted keys, compact separators)."""
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_default(obj: object) -> object:
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")  # type: ignore[no-any-return]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()  # type: ignore[no-any-return]
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def read_json(path: Path) -> JsonValue:
    """Read a JSON document from disk. Raises FileNotFoundError / json.JSONDecodeError."""
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, (dict, list, str, int, float, bool)) and data is not None:
        raise ValueError(f"Unexpected JSON root type: {type(data).__name__}")
    return data  # type: ignore[return-value]


def read_json_object(path: Path) -> dict[str, object]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}, got {type(data).__name__}")
    return data  # type: ignore[return-value]


def atomic_write_bytes(path: Path, data: bytes, *, mode: int = 0o644) -> None:
    """Write bytes via temp + fsync + rename into ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, mode)
        os.replace(str(tmp_path), str(path))
        _fsync_dir(path.parent)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8", mode: int = 0o644) -> None:
    atomic_write_bytes(path, text.encode(encoding), mode=mode)


def atomic_write_json(
    path: Path,
    value: Mapping[str, object] | Sequence[object] | JsonValue,
    *,
    indent: int | None = 2,
) -> str:
    """Atomically write JSON and return the content checksum."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=indent,
        default=_json_default,
    )
    if not payload.endswith("\n"):
        payload = payload + "\n"
    atomic_write_text(path, payload)
    return compute_checksum(value)


def _fsync_dir(directory: Path) -> None:
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)
