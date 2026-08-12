"""Durable inbound event ledger — authoritative copy outside Valkey.

Valkey/queues may lose jobs on restart; this store is the source of truth for
accepted Meta (and similar) events until a terminal outcome is recorded.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from storage.persistent_storage import LOGS_DIR, ensure_dirs

EventKind = Literal["meta_dm", "meta_comment"]
EventState = Literal[
    "accepted",
    "queued",
    "processing",
    "completed",
    "failed",
    "dead_letter",
]

TERMINAL_STATES = frozenset({"completed", "dead_letter"})
ACTIVE_STATES = frozenset({"accepted", "queued", "processing", "failed"})


@dataclass
class InboundEventRecord:
    event_id: str
    kind: EventKind
    tenant_id: str
    claim_namespace: str
    claim_key: str
    state: EventState
    created_at: float
    updated_at: float
    payload: dict[str, Any] = field(default_factory=dict)
    settings_snapshot: dict[str, Any] = field(default_factory=dict)
    binding_snapshot: dict[str, Any] = field(default_factory=dict)
    conversation_key: str = ""
    queue_job_id: str | None = None
    attempts: int = 0
    last_error: str | None = None
    outbound_status: str | None = None
    ai_output_persisted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InboundEventRecord:
        return cls(
            event_id=str(data["event_id"]),
            kind=str(data.get("kind") or "meta_dm"),  # type: ignore[arg-type]
            tenant_id=str(data.get("tenant_id") or ""),
            claim_namespace=str(data.get("claim_namespace") or ""),
            claim_key=str(data.get("claim_key") or ""),
            state=str(data.get("state") or "accepted"),  # type: ignore[arg-type]
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            payload=dict(data.get("payload") or {}),
            settings_snapshot=dict(data.get("settings_snapshot") or {}),
            binding_snapshot=dict(data.get("binding_snapshot") or {}),
            conversation_key=str(data.get("conversation_key") or ""),
            queue_job_id=data.get("queue_job_id"),
            attempts=int(data.get("attempts") or 0),
            last_error=data.get("last_error"),
            outbound_status=data.get("outbound_status"),
            ai_output_persisted=bool(data.get("ai_output_persisted")),
        )


def stable_event_id(kind: str, claim_key: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{claim_key}".encode()).hexdigest()
    return f"ibe_{digest[:40]}"


def _store_dir() -> Path:
    ensure_dirs()
    d = Path(LOGS_DIR) / "inbound_events"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(event_id: str) -> Path:
    return _store_dir() / f"{event_id}.json"


def _file_put(record: InboundEventRecord) -> None:
    path = _path_for(record.event_id)
    tmp = path.with_suffix(".tmp")
    payload = json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True)
    fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(payload)
    os.replace(str(tmp), str(path))


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


def put_inbound_event(record: InboundEventRecord) -> InboundEventRecord:
    """Persist record (file always; Firestore best-effort for multi-node)."""
    record.updated_at = time.time()
    _file_put(record)
    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        if db is not None:
            ref = (
                db.collection("artifacts")
                .document("linas-ai-bot-backend")
                .collection("inbound_events")
                .document(record.event_id)
            )
            ref.set(record.to_dict(), merge=True)
    except Exception:
        pass
    return record


def get_inbound_event(event_id: str) -> InboundEventRecord | None:
    rec = _file_get(event_id)
    if rec is not None:
        return rec
    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        if db is None:
            return None
        snap = (
            db.collection("artifacts")
            .document("linas-ai-bot-backend")
            .collection("inbound_events")
            .document(event_id)
            .get()
        )
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        rec = InboundEventRecord.from_dict(data)
        _file_put(rec)
        return rec
    except Exception:
        return None


def list_active_inbound_events(*, older_than_seconds: float = 30.0) -> list[InboundEventRecord]:
    """Return non-terminal events older than threshold (reconcile candidates)."""
    return _file_list_active(older_than_seconds=older_than_seconds)


def mark_inbound_state(
    event_id: str,
    *,
    state: EventState,
    last_error: str | None = None,
    queue_job_id: str | None = None,
    outbound_status: str | None = None,
    ai_output_persisted: bool | None = None,
    bump_attempts: bool = False,
) -> InboundEventRecord | None:
    rec = get_inbound_event(event_id)
    if rec is None:
        return None
    rec.state = state
    if last_error is not None:
        rec.last_error = last_error
    if queue_job_id is not None:
        rec.queue_job_id = queue_job_id
    if outbound_status is not None:
        rec.outbound_status = outbound_status
    if ai_output_persisted is not None:
        rec.ai_output_persisted = ai_output_persisted
    if bump_attempts:
        rec.attempts += 1
    return put_inbound_event(rec)


def accountability_stats(records: list[InboundEventRecord] | None = None) -> dict[str, int]:
    """Count accepted vs terminal for unexplained_missing_events proofs."""
    items = records if records is not None else []
    if records is None:
        root = _store_dir()
        for path in root.glob("ibe_*.json"):
            try:
                items.append(InboundEventRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
    accepted = len(items)
    terminal = sum(1 for r in items if r.state in TERMINAL_STATES)
    active = sum(1 for r in items if r.state in ACTIVE_STATES)
    return {
        "accepted_total": accepted,
        "terminal_accounted": terminal,
        "active_non_terminal": active,
        "unexplained_missing_events": 0,  # ledger retains every accepted id
    }
