"""Local inbound-event ledger files and process lock."""

from __future__ import annotations

import fcntl
import json
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from services.scale.inbound_event_store_models import ACTIVE_STATES, InboundEventRecord

_LOCAL_LEDGER_THREAD_LOCK = threading.RLock()
_LOCAL_LEDGER_LOCK_STATE = threading.local()


def _store_dir() -> Path:
    # Tests patch LOGS_DIR / ensure_dirs, or replace _store_dir, on the facade.
    from services.scale import inbound_event_store as facade

    patched = getattr(facade, "_store_dir", None)
    if patched is not None and patched is not _store_dir:
        directory = Path(patched())
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    facade.ensure_dirs()
    d = Path(facade.LOGS_DIR) / "inbound_events"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(event_id: str) -> Path:
    return _store_dir() / f"{event_id}.json"


@contextmanager
def local_inbound_event_ledger_lock() -> Iterator[None]:
    """Hold the process/thread-shared exclusive lock for local ledger mutation."""

    with _LOCAL_LEDGER_THREAD_LOCK:
        depth = int(getattr(_LOCAL_LEDGER_LOCK_STATE, "depth", 0))
        if depth:
            _LOCAL_LEDGER_LOCK_STATE.depth = depth + 1
            try:
                yield
            finally:
                _LOCAL_LEDGER_LOCK_STATE.depth = depth
            return

        lock_path = _store_dir() / ".ledger.lock"
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        locked = False
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            locked = True
            _LOCAL_LEDGER_LOCK_STATE.depth = 1
            yield
        finally:
            _LOCAL_LEDGER_LOCK_STATE.depth = 0
            if locked:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _atomic_json_put(path: Path, data: dict[str, Any]) -> None:
    """Replace one ledger file atomically with owner-only permissions."""

    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    payload = json.dumps(data, separators=(",", ":"), sort_keys=True)
    try:
        fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(str(tmp), str(path))
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _file_put(record: InboundEventRecord) -> None:
    path = _path_for(record.event_id)
    with local_inbound_event_ledger_lock():
        document = record.to_dict()
        binding_id = str(
            record.binding_snapshot.get("binding_id") or record.settings_snapshot.get("binding_id") or ""
        ).strip()
        if binding_id:
            from services.meta_inbound_deletion_fence import local_binding_deletion_is_fenced
            from services.meta_inbound_retention import redacted_inbound_event_tombstone

            if local_binding_deletion_is_fenced(binding_id):
                document = redacted_inbound_event_tombstone(
                    document,
                    reason="authorization_data_deletion",
                    now=time.time(),
                )
        _atomic_json_put(path, document)


def iter_local_inbound_event_documents() -> Iterator[tuple[Path, dict[str, Any]]]:
    """Yield parseable mappings; hold the public ledger lock for write batches."""

    for path in _store_dir().glob("ibe_*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict):
            yield path, raw


def replace_local_inbound_event_document(path: Path, data: dict[str, Any]) -> None:
    """Atomically replace one existing ledger document inside the owned store."""

    with local_inbound_event_ledger_lock():
        root = _store_dir().resolve()
        target = path.resolve()
        if target.parent != root or not target.name.startswith("ibe_") or target.suffix != ".json":
            raise ValueError("Refusing to replace a path outside the inbound-event ledger")
        if not target.is_file():
            raise FileNotFoundError("Inbound-event ledger document is unavailable")
        document = data
        binding_snapshot = data.get("binding_snapshot")
        settings_snapshot = data.get("settings_snapshot")
        binding = binding_snapshot if isinstance(binding_snapshot, dict) else {}
        settings = settings_snapshot if isinstance(settings_snapshot, dict) else {}
        binding_id = str(binding.get("binding_id") or settings.get("binding_id") or "").strip()
        if binding_id:
            from services.meta_inbound_deletion_fence import local_binding_deletion_is_fenced
            from services.meta_inbound_retention import redacted_inbound_event_tombstone

            if local_binding_deletion_is_fenced(binding_id):
                document = redacted_inbound_event_tombstone(
                    data,
                    reason="authorization_data_deletion",
                    now=time.time(),
                )
        _atomic_json_put(target, document)


def _file_get(event_id: str) -> InboundEventRecord | None:
    path = _path_for(event_id)
    if not path.is_file():
        return None
    try:
        return InboundEventRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def _file_list_active(*, older_than_seconds: float = 0.0) -> list[InboundEventRecord]:
    cutoff = time.time() - max(0.0, older_than_seconds)
    out: list[InboundEventRecord] = []
    root = _store_dir()
    for path in root.glob("ibe_*.json"):
        try:
            rec = InboundEventRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if rec.state not in ACTIVE_STATES:
            continue
        if rec.updated_at > cutoff:
            continue
        out.append(rec)
    return out
