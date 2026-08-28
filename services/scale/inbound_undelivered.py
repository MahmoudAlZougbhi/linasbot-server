"""Find and reopen Meta DMs marked complete without a Graph send."""

from __future__ import annotations

import json
import logging
import time

from services.scale.inbound_event_store import (
    ACTIVE_STATES,
    InboundEventRecord,
    InboundEventStateTransitionError,
    get_inbound_event,
    put_inbound_event,
)

_logger = logging.getLogger(__name__)

_UNDELIVERED_OUTBOUND = frozenset({"unknown", "needs_owner_action", "undelivered_retry"})
_DELIVERED_OUTBOUND = frozenset({"sent", "delivered", "simulated"})
_MAX_AGE_SECONDS = 7 * 24 * 3600


def is_completed_undelivered(rec: InboundEventRecord) -> bool:
    if rec.kind != "meta_dm":
        return False
    if rec.state != "completed":
        return False
    if bool((rec.payload or {}).get("_linas_soak_simulation")):
        return False
    outbound = str(rec.outbound_status or "").strip().lower()
    if outbound in _DELIVERED_OUTBOUND:
        return False
    return outbound in _UNDELIVERED_OUTBOUND


def combine_user_key_for_event(rec: InboundEventRecord) -> str:
    from services.social_user_id import compose_social_user_id

    payload = rec.payload or {}
    channel = str(payload.get("channel") or rec.binding_snapshot.get("channel") or "").strip().lower()
    sender = str(payload.get("sender_id") or "").strip()
    settings = rec.settings_snapshot or {}
    binding = rec.binding_snapshot or {}
    if channel == "instagram":
        asset = str(settings.get("instagram_account_id") or binding.get("instagram_account_id") or "")
    else:
        asset = str(settings.get("page_id") or binding.get("page_id") or "")
    return compose_social_user_id(
        tenant_id=rec.tenant_id,
        channel=channel,
        asset_id=asset,
        sender_id=sender,
    )


def forget_combine_seen_for_event(rec: InboundEventRecord) -> None:
    from services.scale.message_combine_store import forget_seen

    mid = str((rec.payload or {}).get("message_id") or "")
    keys: list[str] = []
    try:
        keys.append(combine_user_key_for_event(rec))
    except Exception:
        _logger.warning("[undelivered] combine_user_key_failed event_id=%s", rec.event_id)
    conv = str(rec.conversation_key or "").strip()
    if conv and conv not in keys:
        keys.append(conv)
    for user_key in keys:
        forget_seen(user_key, event_id=rec.event_id, mid=mid)


def reopen_completed_undelivered(event_id: str) -> InboundEventRecord:
    from config import is_production_runtime

    require_shared = bool(is_production_runtime())
    rec = get_inbound_event(event_id, require_shared_authority=require_shared)
    if rec is None:
        raise InboundEventStateTransitionError("Inbound event is unavailable for undelivered reopen")
    if rec.state in ACTIVE_STATES:
        return rec
    if not is_completed_undelivered(rec):
        raise InboundEventStateTransitionError("Inbound event cannot be reopened")
    rec.state = "accepted"
    rec.outbound_status = "undelivered_retry"
    rec.last_error = None
    rec.attempts += 1
    return put_inbound_event(rec, require_shared_existing=require_shared)


def _age_ok(rec: InboundEventRecord, *, older_than_seconds: float, now: float) -> bool:
    if rec.updated_at > now - max(0.0, older_than_seconds):
        return False
    if rec.updated_at < now - _MAX_AGE_SECONDS:
        return False
    return True


def _list_local_completed_undelivered(*, older_than_seconds: float, now: float) -> list[InboundEventRecord]:
    from services.scale.inbound_event_store import _store_dir

    out: list[InboundEventRecord] = []
    for path in _store_dir().glob("ibe_*.json"):
        try:
            rec = InboundEventRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if is_completed_undelivered(rec) and _age_ok(rec, older_than_seconds=older_than_seconds, now=now):
            out.append(rec)
    return out


def _list_shared_completed_undelivered(*, older_than_seconds: float, now: float) -> list[InboundEventRecord]:
    from google.cloud.firestore_v1.base_query import FieldFilter

    from services.scale.inbound_event_store import _firestore_inbound_collection, _record_from_firestore_snapshot
    from utils.utils import get_firestore_db

    db = get_firestore_db()
    if db is None:
        return []
    collection = _firestore_inbound_collection(db)
    found: dict[str, InboundEventRecord] = {}
    for status in ("unknown", "needs_owner_action"):
        query = collection.where(filter=FieldFilter("outbound_status", "==", status))
        for snapshot in query.stream():
            rec = _record_from_firestore_snapshot(snapshot)
            if rec is None:
                continue
            if is_completed_undelivered(rec) and _age_ok(rec, older_than_seconds=older_than_seconds, now=now):
                found[rec.event_id] = rec
    return list(found.values())


def list_completed_undelivered_meta_dms(*, older_than_seconds: float = 60.0) -> list[InboundEventRecord]:
    now = time.time()
    by_id: dict[str, InboundEventRecord] = {}
    for rec in _list_local_completed_undelivered(older_than_seconds=older_than_seconds, now=now):
        by_id[rec.event_id] = rec
    try:
        for rec in _list_shared_completed_undelivered(older_than_seconds=older_than_seconds, now=now):
            by_id[rec.event_id] = rec
    except Exception as exc:
        _logger.warning("[undelivered] shared_scan_failed type=%s", type(exc).__name__)
    live: list[InboundEventRecord] = []
    for rec in by_id.values():
        current = get_inbound_event(rec.event_id)
        if current is None:
            continue
        if is_completed_undelivered(current) and _age_ok(current, older_than_seconds=older_than_seconds, now=now):
            live.append(current)
    return sorted(live, key=lambda item: (item.updated_at, item.event_id))
