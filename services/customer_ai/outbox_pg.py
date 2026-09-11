"""Optional SQL persistence for Brain outbox envelopes. Never regenerates text."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import bindparam, text

from services.customer_ai.outbox import OutboxItem


def table_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            row = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_ai_outbox'")
            ).first()
            return bool(row and row[0])
        row = session.execute(text("SELECT to_regclass('customer_ai_outbox')")).first()
        return bool(row and row[0])
    except Exception:
        return False


def pg_reset(session: Any) -> None:
    session.execute(text("DELETE FROM customer_ai_outbox"))


def pg_upsert(session: Any, item: OutboxItem) -> None:
    envelope = json.dumps(item.envelope or {}, ensure_ascii=False)
    extra = json.dumps(item.extra or {}, ensure_ascii=False)
    session.execute(
        text(
            "INSERT INTO customer_ai_outbox ("
            "outbox_id, tenant_id, operation_id, reservation_id, billing_policy, state, "
            "envelope, provider_message_id, attempts, updated_at, extra"
            ") VALUES ("
            ":outbox_id, :tenant_id, :operation_id, :reservation_id, :billing_policy, :state, "
            ":envelope, :provider_message_id, :attempts, :updated_at, :extra"
            ") ON CONFLICT (outbox_id) DO UPDATE SET "
            "state=:state, provider_message_id=:provider_message_id, "
            "attempts=:attempts, updated_at=:updated_at, extra=:extra"
        ),
        {
            "outbox_id": item.outbox_id,
            "tenant_id": item.tenant_id,
            "operation_id": item.operation_id,
            "reservation_id": item.reservation_id,
            "billing_policy": item.billing_policy,
            "state": item.state,
            "envelope": envelope,
            "provider_message_id": item.provider_message_id,
            "attempts": item.attempts,
            "updated_at": item.updated_at,
            "extra": extra,
        },
    )


def _decode(raw: Any, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    value = raw if raw is not None else fallback
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = fallback or {}
    return dict(value) if isinstance(value, dict) else dict(fallback or {})


def _row(raw: Any) -> OutboxItem:
    return OutboxItem(
        outbox_id=str(raw["outbox_id"]),
        tenant_id=str(raw.get("tenant_id") or ""),
        operation_id=str(raw.get("operation_id") or ""),
        reservation_id=str(raw.get("reservation_id") or ""),
        billing_policy=str(raw.get("billing_policy") or "legacy_credits"),
        state=raw.get("state") or "accepted",
        envelope=_decode(raw.get("envelope")),
        provider_message_id=str(raw.get("provider_message_id") or ""),
        attempts=int(raw.get("attempts") or 0),
        updated_at=str(raw.get("updated_at") or ""),
        extra=_decode(raw.get("extra")),
    )


def pg_list(
    session: Any,
    *,
    states: tuple[str, ...],
    limit: int,
    tenant_id: str = "",
) -> list[OutboxItem]:
    sql = (
        "SELECT outbox_id, tenant_id, operation_id, reservation_id, billing_policy, state, "
        "envelope, provider_message_id, attempts, updated_at, extra "
        "FROM customer_ai_outbox WHERE state IN :states"
    )
    params: dict[str, Any] = {"states": tuple(states), "lim": limit}
    if tenant_id:
        sql += " AND tenant_id = :tid"
        params["tid"] = tenant_id
    sql += " ORDER BY outbox_id LIMIT :lim"
    stmt = text(sql).bindparams(bindparam("states", expanding=True))
    rows = session.execute(stmt, params).mappings().all()
    return [_row(dict(row)) for row in rows]


def pg_get(session: Any, outbox_id: str) -> OutboxItem | None:
    row = (
        session.execute(
            text(
                "SELECT outbox_id, tenant_id, operation_id, reservation_id, billing_policy, state, "
                "envelope, provider_message_id, attempts, updated_at, extra "
                "FROM customer_ai_outbox WHERE outbox_id = :oid"
            ),
            {"oid": outbox_id},
        )
        .mappings()
        .first()
    )
    return _row(dict(row)) if row else None


def pg_tenant_ids(session: Any) -> list[str]:
    rows = session.execute(text("SELECT DISTINCT tenant_id FROM customer_ai_outbox")).all()
    return sorted(str(row[0]) for row in rows if row and row[0])


def pg_outbox_ids(session: Any, *, tenant_id: str = "") -> set[str]:
    sql = "SELECT outbox_id FROM customer_ai_outbox"
    params: dict[str, Any] = {}
    if tenant_id:
        sql += " WHERE tenant_id = :tid"
        params["tid"] = tenant_id
    return {str(row[0]) for row in session.execute(text(sql), params).all() if row and row[0]}


def pg_counts(session: Any, *, tenant_id: str = "") -> dict[str, int]:
    sql = "SELECT state, COUNT(*) AS n FROM customer_ai_outbox"
    params: dict[str, Any] = {}
    if tenant_id:
        sql += " WHERE tenant_id = :tid"
        params["tid"] = tenant_id
    sql += " GROUP BY state"
    counts = {"accepted": 0, "sent": 0, "pending_settlement": 0, "failed": 0}
    for row in session.execute(text(sql), params).mappings().all():
        counts[str(row["state"])] = int(row["n"] or 0)
    return counts
