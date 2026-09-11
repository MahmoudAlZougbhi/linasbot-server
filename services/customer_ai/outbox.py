"""Durable Brain envelope outbox. Recover the same envelope; never regenerate."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from services.customer_ai.contracts.reply import FinalReplyEnvelope, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn

OutboxState = Literal["accepted", "sent", "failed", "pending_settlement"]

_LOCK = threading.Lock()
_HYDRATED = False


@dataclass
class OutboxItem:
    outbox_id: str
    tenant_id: str
    operation_id: str
    reservation_id: str
    billing_policy: str
    state: OutboxState
    envelope: dict[str, Any]
    provider_message_id: str = ""
    attempts: int = 0
    updated_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


_ITEMS: dict[str, OutboxItem] = {}


def reset_outbox_for_tests() -> None:
    global _HYDRATED
    with _LOCK:
        _ITEMS.clear()
        _HYDRATED = True
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.customer_ai.outbox_pg import pg_reset, table_ready

        if table_ready(session):
            pg_reset(session)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _root() -> Path:
    root = (os.getenv("LINASBOT_DATA_ROOT") or os.getenv("LINAS_DATA_ROOT") or "").strip()
    if not root:
        from storage.persistent_storage import _DATA_ROOT

        root = str(_DATA_ROOT)
    path = Path(root) / "customer_ai_outbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _memory_forced() -> bool:
    from services.membership.pg_store import memory_forced

    return memory_forced()


def _persist(item: OutboxItem) -> None:
    if _memory_forced():
        return
    try:
        (_root() / f"{item.outbox_id.replace(':', '_')}.json").write_text(
            json.dumps(asdict(item), ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass
    _persist_pg(item)


def _persist_pg(item: OutboxItem) -> None:
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.customer_ai.outbox_pg import pg_upsert, table_ready

        if table_ready(session):
            pg_upsert(session, item)


def _item_from_disk(data: dict[str, Any], path_stem: str) -> OutboxItem:
    oid = str(data.get("outbox_id") or path_stem.replace("_", ":", 1))
    return OutboxItem(
        outbox_id=oid,
        tenant_id=str(data.get("tenant_id") or ""),
        operation_id=str(data.get("operation_id") or ""),
        reservation_id=str(data.get("reservation_id") or ""),
        billing_policy=str(data.get("billing_policy") or "legacy_credits"),
        state=data.get("state") or "accepted",
        envelope=dict(data.get("envelope") or {}),
        provider_message_id=str(data.get("provider_message_id") or ""),
        attempts=int(data.get("attempts") or 0),
        updated_at=str(data.get("updated_at") or _now()),
        extra=dict(data.get("extra") or {}),
    )


def _hydrate() -> None:
    global _HYDRATED
    if _HYDRATED or _memory_forced():
        return
    loaded: dict[str, OutboxItem] = {}
    sql_known: set[str] = set()
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is not None:
            from services.customer_ai.outbox_pg import pg_list, pg_outbox_ids, table_ready

            if table_ready(session):
                for item in pg_list(
                    session,
                    states=("accepted", "pending_settlement", "sent", "failed"),
                    limit=2000,
                ):
                    loaded[item.outbox_id] = item
                sql_known.update(pg_outbox_ids(session))
    for path in _root().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            item = _item_from_disk(data, path.stem)
            if item.outbox_id in loaded or item.outbox_id in sql_known:
                continue
            loaded[item.outbox_id] = item
        except Exception:
            continue
    with _LOCK:
        if not _HYDRATED:
            _ITEMS.update(loaded)
            _HYDRATED = True
    _promote_missing_to_pg()


def _promote_missing_to_pg() -> None:
    if _memory_forced() or not _ITEMS:
        return
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.customer_ai.outbox_pg import pg_get, pg_upsert, table_ready

        if not table_ready(session):
            return
        with _LOCK:
            items = list(_ITEMS.values())
        for item in items:
            if pg_get(session, item.outbox_id) is None:
                pg_upsert(session, item)


def outbox_id_for(tenant_id: str, operation_id: str) -> str:
    return f"{tenant_id}:{operation_id}"


def _get(oid: str) -> OutboxItem | None:
    if not _memory_forced():
        from services.membership.pg_store import optional_message_session

        with optional_message_session() as session:
            if session is not None:
                from services.customer_ai.outbox_pg import pg_get, table_ready

                if table_ready(session):
                    found = pg_get(session, oid)
                    if found is not None:
                        with _LOCK:
                            _ITEMS[oid] = found
                        return found
    with _LOCK:
        return _ITEMS.get(oid)


def enqueue_envelope(
    *,
    tenant_id: str,
    operation_id: str,
    envelope: FinalReplyEnvelope,
    reservation_id: str = "",
    billing_policy: str = "legacy_credits",
    extra: dict[str, Any] | None = None,
) -> OutboxItem:
    _hydrate()
    oid = outbox_id_for(tenant_id, operation_id)
    existing = _get(oid)
    if existing is not None:
        return existing
    payload = envelope.model_dump()
    with _LOCK:
        current = _ITEMS.get(oid)
        if current is not None:
            return current
        item = OutboxItem(
            outbox_id=oid,
            tenant_id=tenant_id,
            operation_id=operation_id,
            reservation_id=reservation_id,
            billing_policy=billing_policy,
            state="accepted",
            envelope=payload,
            updated_at=_now(),
            extra=dict(extra or {}),
        )
        _ITEMS[oid] = item
        _persist(item)
        return item


def persist_turn_result(turn: CustomerTurn, result: TurnResult) -> OutboxItem | None:
    if not any((item.text or "").strip() for item in result.envelope.messages):
        return None
    extra = dict(result.extra or {})
    op = str(extra.get("operation_id") or "").strip()
    if not op:
        return None
    inbound = ""
    if turn.history.messages:
        current = next((m for m in reversed(turn.history.messages) if m.is_current_inbound), None)
        inbound = (current.text if current else turn.history.messages[-1].text) or ""
    if not inbound and turn.followup_goal:
        inbound = f"Follow-up: {turn.followup_goal}"
    return enqueue_envelope(
        tenant_id=turn.tenant_id,
        operation_id=op,
        envelope=result.envelope,
        reservation_id=op,
        billing_policy=str(extra.get("billing_policy") or "legacy_credits"),
        extra={
            "channel": turn.channel,
            "conversation_id": turn.conversation_id,
            "surface": turn.surface,
            "invocation_kind": turn.invocation_kind,
            "inbound_preview": (inbound or "")[:280],
            "phase": extra.get("phase"),
            "stop_reason": result.stop_reason,
            "message_units": extra.get("message_units"),
            "response_class": extra.get("response_class"),
            "billing_policy": extra.get("billing_policy"),
            "used_evidence_ids": extra.get("used_evidence_ids") or result.envelope.used_evidence_ids,
            "evidence_preview": extra.get("evidence_preview") or [],
            "stage_timeline": extra.get("stage_timeline") or [],
            "plan_tasks": [
                {"id": task.get("id"), "type": task.get("type")}
                for task in ((extra.get("plan") or {}).get("tasks") or [])
                if isinstance(task, dict)
            ],
        },
    )


def list_recent(*, tenant_id: str = "", limit: int = 50) -> list[OutboxItem]:
    _hydrate()
    tid = (tenant_id or "").strip()
    rows = [item for item in _ITEMS.values() if not tid or item.tenant_id == tid]
    rows.sort(key=lambda item: item.updated_at, reverse=True)
    return rows[: max(1, min(int(limit or 50), 200))]


def mark_sent(outbox_id: str, *, provider_message_id: str = "") -> OutboxItem | None:
    _hydrate()
    item = _get(outbox_id)
    with _LOCK:
        if item is None:
            return None
        item.state = "sent"
        item.provider_message_id = provider_message_id or item.provider_message_id
        item.updated_at = _now()
        _persist(item)
        return item


def mark_failed(outbox_id: str) -> OutboxItem | None:
    _hydrate()
    item = _get(outbox_id)
    with _LOCK:
        if item is None:
            return None
        if item.state in {"sent", "pending_settlement"}:
            return item
        item.state = "failed"
        item.updated_at = _now()
        _persist(item)
        return item


def mark_pending_settlement(outbox_id: str) -> OutboxItem | None:
    _hydrate()
    item = _get(outbox_id)
    with _LOCK:
        if item is None:
            return None
        if item.state not in {"sent", "accepted"}:
            return item
        item.state = "pending_settlement"
        item.updated_at = _now()
        _persist(item)
        return item


def _lookup_ids(tenant_id: str, operation_id: str, extra_ids: tuple[str, ...] | list[str]) -> list[str]:
    seen: list[str] = []
    for item in (operation_id, *extra_ids):
        text = str(item or "").strip()
        if text and text not in seen:
            seen.append(outbox_id_for(tenant_id, text))
    return seen


def acknowledge_sent(
    *,
    tenant_id: str,
    operation_id: str = "",
    provider_message_id: str = "",
    extra_ids: tuple[str, ...] | list[str] = (),
) -> OutboxItem | None:
    if not tenant_id:
        return None
    for oid in _lookup_ids(tenant_id, operation_id, extra_ids):
        found = mark_sent(oid, provider_message_id=provider_message_id)
        if found is not None:
            return found
    return None


def acknowledge_failed(
    *,
    tenant_id: str,
    operation_id: str = "",
    extra_ids: tuple[str, ...] | list[str] = (),
) -> OutboxItem | None:
    if not tenant_id:
        return None
    for oid in _lookup_ids(tenant_id, operation_id, extra_ids):
        found = mark_failed(oid)
        if found is not None:
            return found
    return None


def known_outbox_tenant_ids() -> list[str]:
    """Tenants already present on outbox rows. Do not invent ids."""
    ids: set[str] = set()
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is not None:
            from services.customer_ai.outbox_pg import pg_tenant_ids, table_ready

            if table_ready(session):
                ids.update(pg_tenant_ids(session))
    _hydrate()
    with _LOCK:
        ids.update(item.tenant_id for item in _ITEMS.values() if item.tenant_id)
    return sorted(ids)


def acknowledge_pending_settlement(
    *,
    tenant_id: str,
    operation_id: str = "",
    provider_message_id: str = "",
    extra_ids: tuple[str, ...] | list[str] = (),
) -> OutboxItem | None:
    if not tenant_id:
        return None
    acknowledge_sent(
        tenant_id=tenant_id,
        operation_id=operation_id,
        provider_message_id=provider_message_id,
        extra_ids=extra_ids,
    )
    for oid in _lookup_ids(tenant_id, operation_id, extra_ids):
        found = mark_pending_settlement(oid)
        if found is not None:
            return found
    return None


def _list_pg(*, states: tuple[str, ...], tenant_id: str, limit: int) -> list[OutboxItem] | None:
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return None
        from services.customer_ai.outbox_pg import pg_list, table_ready

        if not table_ready(session):
            return None
        return pg_list(session, states=states, limit=limit, tenant_id=tenant_id)


def _sql_known_ids(*, tenant_id: str = "") -> set[str]:
    try:
        from services.membership.pg_store import optional_message_session

        with optional_message_session() as session:
            if session is None:
                return set()
            from services.customer_ai.outbox_pg import pg_outbox_ids, table_ready

            if not table_ready(session):
                return set()
            return pg_outbox_ids(session, tenant_id=tenant_id)
    except Exception:
        return set()


def _recover(state: OutboxState, *, tenant_id: str, limit: int) -> list[OutboxItem]:
    cap = max(1, min(int(limit), 200))
    tid = tenant_id.strip()
    rows: list[OutboxItem] = []
    seen: set[str] = set()
    pg_rows = _list_pg(states=(state,), tenant_id=tid, limit=cap)
    if pg_rows is not None:
        rows.extend(pg_rows)
        seen.update(item.outbox_id for item in pg_rows)
        seen.update(_sql_known_ids(tenant_id=tid))
    _hydrate()
    with _LOCK:
        for item in _ITEMS.values():
            if item.state != state or item.outbox_id in seen:
                continue
            if tid and item.tenant_id != tid:
                continue
            rows.append(item)
            seen.add(item.outbox_id)
    rows.sort(key=lambda item: item.outbox_id)
    return rows[:cap]


def recover_unsent(*, tenant_id: str = "", limit: int = 50) -> list[OutboxItem]:
    return _recover("accepted", tenant_id=tenant_id, limit=limit)


def recover_pending_settlement(*, tenant_id: str = "", limit: int = 50) -> list[OutboxItem]:
    return _recover("pending_settlement", tenant_id=tenant_id, limit=limit)


def outbox_counts(*, tenant_id: str = "") -> dict[str, int]:
    tid = tenant_id.strip()
    counts = {"accepted": 0, "sent": 0, "pending_settlement": 0, "failed": 0}
    seen: set[str] = set()
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is not None:
            from services.customer_ai.outbox_pg import pg_counts, pg_outbox_ids, table_ready

            if table_ready(session):
                counts.update(pg_counts(session, tenant_id=tid))
                seen.update(pg_outbox_ids(session, tenant_id=tid))
    _hydrate()
    with _LOCK:
        for item in _ITEMS.values():
            if item.outbox_id in seen:
                continue
            if tid and item.tenant_id != tid:
                continue
            counts[item.state] = counts.get(item.state, 0) + 1
    return counts


def envelope_from_item(item: OutboxItem) -> FinalReplyEnvelope:
    return FinalReplyEnvelope.model_validate(item.envelope)
