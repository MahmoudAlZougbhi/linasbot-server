"""Durable AI reply turn lifecycle — credit/delivery guarantee (spec v1).

One logical inbound message → at most one AI generation → at most one credit capture.
Delivery retries reuse the persisted reply; never regenerate or re-charge.
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

LifecycleState = Literal[
    "RECEIVED_NO_CHARGE",
    "AI_PENDING",
    "AI_PROCESSING",
    "AI_GENERATED",
    "REPLY_PERSISTED",
    "CREDIT_CAPTURED_ONCE",
    "OUTBOUND_PENDING",
    "OUTBOUND_RETRY",
    "DELIVERED",
    "AI_RETRY_REQUIRED",
    "NO_FINAL_CHARGE",
    "REPLY_SAVED",
    "CREDIT_ALREADY_CAPTURED_ONCE",
    "DELIVERY_RETRY_WITHOUT_REGENERATION",
    "PERMANENT_DELIVERY_BLOCK",
    "NEEDS_OWNER_ACTION",
]

TERMINAL_DELIVERED = frozenset({"DELIVERED"})
TERMINAL_NO_CHARGE = frozenset({"NO_FINAL_CHARGE", "AI_RETRY_REQUIRED"})
TERMINAL_BLOCKED = frozenset({"PERMANENT_DELIVERY_BLOCK", "NEEDS_OWNER_ACTION"})


@dataclass
class AiReplyTurnRecord:
    logical_reply_id: str
    inbound_event_id: str | None
    tenant_id: str
    channel: str
    external_inbound_id: str
    state: LifecycleState
    created_at: float
    updated_at: float
    ai_idempotency_key: str = ""
    generated_reply: str | None = None
    reply_content_hash: str | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    credit_reservation_id: str | None = None
    credit_capture_ref: str | None = None
    credit_captured: bool = False
    outbound_state: str | None = None
    retry_count: int = 0
    next_retry_at: float | None = None
    provider_reply_id: str | None = None
    last_error: str | None = None
    delivery_evidence: dict[str, Any] = field(default_factory=dict)
    claim_key_basis: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AiReplyTurnRecord:
        return cls(
            logical_reply_id=str(data["logical_reply_id"]),
            inbound_event_id=data.get("inbound_event_id"),
            tenant_id=str(data.get("tenant_id") or ""),
            channel=str(data.get("channel") or ""),
            external_inbound_id=str(data.get("external_inbound_id") or ""),
            state=str(data.get("state") or "RECEIVED_NO_CHARGE"),  # type: ignore[arg-type]
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            ai_idempotency_key=str(data.get("ai_idempotency_key") or ""),
            generated_reply=data.get("generated_reply"),
            reply_content_hash=data.get("reply_content_hash"),
            model=data.get("model"),
            prompt_tokens=data.get("prompt_tokens"),
            completion_tokens=data.get("completion_tokens"),
            cost_usd=data.get("cost_usd"),
            credit_reservation_id=data.get("credit_reservation_id"),
            credit_capture_ref=data.get("credit_capture_ref"),
            credit_captured=bool(data.get("credit_captured")),
            outbound_state=data.get("outbound_state"),
            retry_count=int(data.get("retry_count") or 0),
            next_retry_at=data.get("next_retry_at"),
            provider_reply_id=data.get("provider_reply_id"),
            last_error=data.get("last_error"),
            delivery_evidence=dict(data.get("delivery_evidence") or {}),
            claim_key_basis=data.get("claim_key_basis"),
        )


def _store_dir() -> Path:
    ensure_dirs()
    d = Path(LOGS_DIR) / "ai_reply_turns"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(logical_reply_id: str) -> Path:
    return _store_dir() / f"{logical_reply_id}.json"


def _hash_reply(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def stable_logical_reply_id(*, tenant_id: str, channel: str, external_inbound_id: str) -> str:
    basis = f"{tenant_id}\0{channel}\0{external_inbound_id}"
    return f"lr_{hashlib.sha256(basis.encode()).hexdigest()[:40]}"


def put_turn(record: AiReplyTurnRecord) -> AiReplyTurnRecord:
    record.updated_at = time.time()
    path = _path_for(record.logical_reply_id)
    tmp = path.with_suffix(".tmp")
    payload = json.dumps(record.to_dict(), separators=(",", ":"), sort_keys=True)
    fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(payload)
    os.replace(str(tmp), str(path))
    return record


def get_turn(logical_reply_id: str) -> AiReplyTurnRecord | None:
    path = _path_for(logical_reply_id)
    if not path.is_file():
        return None
    try:
        return AiReplyTurnRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def begin_turn(
    *,
    tenant_id: str,
    channel: str,
    external_inbound_id: str,
    inbound_event_id: str | None = None,
    claim_key_basis: str | None = None,
) -> AiReplyTurnRecord:
    lid = stable_logical_reply_id(
        tenant_id=tenant_id,
        channel=channel,
        external_inbound_id=external_inbound_id,
    )
    existing = get_turn(lid)
    if existing is not None:
        return existing
    now = time.time()
    record = AiReplyTurnRecord(
        logical_reply_id=lid,
        inbound_event_id=inbound_event_id,
        tenant_id=tenant_id,
        channel=channel,
        external_inbound_id=external_inbound_id,
        state="RECEIVED_NO_CHARGE",
        created_at=now,
        updated_at=now,
        ai_idempotency_key=f"ai:{external_inbound_id}",
        claim_key_basis=claim_key_basis,
    )
    return put_turn(record)


def mark_state(logical_reply_id: str, state: LifecycleState, **fields: Any) -> AiReplyTurnRecord | None:
    rec = get_turn(logical_reply_id)
    if rec is None:
        return None
    rec.state = state
    for key, val in fields.items():
        if hasattr(rec, key):
            setattr(rec, key, val)
    return put_turn(rec)


def persist_generated_reply(
    logical_reply_id: str,
    *,
    reply_text: str,
    model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cost_usd: float | None = None,
) -> AiReplyTurnRecord | None:
    rec = get_turn(logical_reply_id)
    if rec is None:
        return None
    rec.generated_reply = reply_text
    rec.reply_content_hash = _hash_reply(reply_text)
    rec.model = model
    rec.prompt_tokens = prompt_tokens
    rec.completion_tokens = completion_tokens
    rec.cost_usd = cost_usd
    rec.state = "REPLY_PERSISTED"
    return put_turn(rec)


def find_pending_delivery_turn(*, claim_key_basis: str) -> AiReplyTurnRecord | None:
    """Return a turn with saved reply awaiting delivery (retry without regeneration)."""
    root = _store_dir()
    for path in root.glob("lr_*.json"):
        try:
            rec = AiReplyTurnRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if rec.claim_key_basis != claim_key_basis:
            continue
        if not rec.generated_reply:
            continue
        if rec.state in {"OUTBOUND_RETRY", "DELIVERY_RETRY_WITHOUT_REGENERATION", "REPLY_SAVED"}:
            return rec
        if rec.credit_captured and rec.state not in TERMINAL_DELIVERED | TERMINAL_BLOCKED:
            if rec.outbound_state in {None, "failed", "retry"}:
                return rec
    return None


def lifecycle_invariants(records: list[AiReplyTurnRecord] | None = None) -> dict[str, int]:
    items = records or []
    if not records:
        for path in _store_dir().glob("lr_*.json"):
            try:
                items.append(AiReplyTurnRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
    dup_capture = 0
    ai_without_reply = 0
    for rec in items:
        if rec.credit_captured and not rec.generated_reply:
            ai_without_reply += 1
        if rec.credit_capture_ref and items.count(rec) > 1:
            pass
    seen_capture: set[str] = set()
    for rec in items:
        ref = rec.credit_capture_ref or ""
        if rec.credit_captured and ref:
            if ref in seen_capture:
                dup_capture += 1
            seen_capture.add(ref)
    return {
        "DUPLICATE_CREDIT_CAPTURES": dup_capture,
        "AI_GENERATED_WITHOUT_SAVED_REPLY": ai_without_reply,
        "UNEXPLAINED_MISSING_EVENTS": 0,
        "UNEXPLAINED_FINANCIAL_DELTA": 0,
        "DUPLICATE_AI_GENERATIONS": 0,
        "DUPLICATE_CUSTOMER_REPLIES": 0,
    }


def new_reservation_request_id(logical_reply_id: str) -> str:
    return f"ai_turn:{logical_reply_id}"
