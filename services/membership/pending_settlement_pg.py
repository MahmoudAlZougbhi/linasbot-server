"""Optional SQL persistence for pending settlements. Paginated; no tenant guess."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import bindparam, text

from services.membership.pending_settlement import PendingSettlement


def table_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            row = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_ai_pending_settlements'")
            ).first()
            return bool(row and row[0])
        row = session.execute(text("SELECT to_regclass('customer_ai_pending_settlements')")).first()
        return bool(row and row[0])
    except Exception:
        return False


def pg_reset(session: Any) -> None:
    session.execute(text("DELETE FROM customer_ai_pending_settlements"))


def pg_upsert(session: Any, item: PendingSettlement) -> None:
    extra = json.dumps(item.extra or {}, ensure_ascii=False)
    session.execute(
        text(
            "INSERT INTO customer_ai_pending_settlements ("
            "settlement_id, tenant_id, reservation_id, operation_id, billing_policy, state, "
            "created_at, updated_at, attempts, send_status, provider_message_id, channel, reason, extra"
            ") VALUES ("
            ":settlement_id, :tenant_id, :reservation_id, :operation_id, :billing_policy, :state, "
            ":created_at, :updated_at, :attempts, :send_status, :provider_message_id, :channel, :reason, :extra"
            ") ON CONFLICT (settlement_id) DO UPDATE SET "
            "state=:state, updated_at=:updated_at, attempts=:attempts, send_status=:send_status, "
            "provider_message_id=:provider_message_id, channel=:channel, reason=:reason, extra=:extra"
        ),
        {
            "settlement_id": item.settlement_id,
            "tenant_id": item.tenant_id,
            "reservation_id": item.reservation_id,
            "operation_id": item.operation_id,
            "billing_policy": item.billing_policy,
            "state": item.state,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "attempts": item.attempts,
            "send_status": item.send_status,
            "provider_message_id": item.provider_message_id,
            "channel": item.channel,
            "reason": item.reason,
            "extra": extra,
        },
    )


def _row(raw: Any) -> PendingSettlement:
    extra = raw.get("extra") or {}
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}
    return PendingSettlement(
        settlement_id=str(raw["settlement_id"]),
        tenant_id=str(raw["tenant_id"]),
        reservation_id=str(raw.get("reservation_id") or ""),
        operation_id=str(raw.get("operation_id") or ""),
        billing_policy=raw.get("billing_policy") or "legacy_credits",
        state=raw.get("state") or "reserved",
        created_at=str(raw.get("created_at") or ""),
        updated_at=str(raw.get("updated_at") or ""),
        attempts=int(raw.get("attempts") or 0),
        send_status=str(raw.get("send_status") or ""),
        provider_message_id=str(raw.get("provider_message_id") or ""),
        channel=str(raw.get("channel") or ""),
        reason=str(raw.get("reason") or ""),
        extra=dict(extra) if isinstance(extra, dict) else {},
    )


def pg_list(
    session: Any,
    *,
    states: tuple[str, ...],
    limit: int,
    after_id: str = "",
    tenant_id: str = "",
) -> list[PendingSettlement]:
    sql = (
        "SELECT settlement_id, tenant_id, reservation_id, operation_id, billing_policy, state, "
        "created_at, updated_at, attempts, send_status, provider_message_id, channel, reason, extra "
        "FROM customer_ai_pending_settlements WHERE state IN :states AND settlement_id > :after"
    )
    params: dict[str, Any] = {"states": tuple(states), "after": after_id or "", "lim": limit}
    if tenant_id:
        sql += " AND tenant_id = :tid"
        params["tid"] = tenant_id
    sql += " ORDER BY settlement_id LIMIT :lim"
    stmt = text(sql).bindparams(bindparam("states", expanding=True))
    rows = session.execute(stmt, params).mappings().all()
    return [_row(dict(row)) for row in rows]


def pg_counts(session: Any, *, tenant_id: str = "") -> dict[str, int]:
    sql = "SELECT state, COUNT(*) AS n FROM customer_ai_pending_settlements"
    params: dict[str, Any] = {}
    if tenant_id:
        sql += " WHERE tenant_id = :tid"
        params["tid"] = tenant_id
    sql += " GROUP BY state"
    counts = {"reserved": 0, "pending_settlement": 0, "settled": 0, "released": 0, "unresolved": 0}
    for row in session.execute(text(sql), params).mappings().all():
        counts[str(row["state"])] = int(row["n"] or 0)
    return counts


def pg_tenant_ids(session: Any) -> list[str]:
    rows = session.execute(text("SELECT DISTINCT tenant_id FROM customer_ai_pending_settlements")).all()
    return sorted(str(row[0]) for row in rows if row and row[0])


def pg_settlement_ids(session: Any, *, tenant_id: str = "") -> set[str]:
    sql = "SELECT settlement_id FROM customer_ai_pending_settlements"
    params: dict[str, Any] = {}
    if tenant_id:
        sql += " WHERE tenant_id = :tid"
        params["tid"] = tenant_id
    return {str(row[0]) for row in session.execute(text(sql), params).all() if row and row[0]}


def pg_policy_for(session: Any, tenant_id: str, operation_ids: set[str]) -> str | None:
    if not tenant_id or not operation_ids:
        return None
    stmt = text(
        "SELECT billing_policy FROM customer_ai_pending_settlements "
        "WHERE tenant_id = :tid AND state IN ('reserved', 'pending_settlement') "
        "AND (operation_id IN :ops OR reservation_id IN :ops) "
        "ORDER BY settlement_id LIMIT 1"
    ).bindparams(bindparam("ops", expanding=True))
    row = session.execute(stmt, {"tid": tenant_id, "ops": tuple(operation_ids)}).mappings().first()
    if row and row.get("billing_policy"):
        return str(row["billing_policy"])
    rows = (
        session.execute(
            text(
                "SELECT billing_policy, extra FROM customer_ai_pending_settlements "
                "WHERE tenant_id = :tid AND state IN ('reserved', 'pending_settlement')"
            ),
            {"tid": tenant_id},
        )
        .mappings()
        .all()
    )
    wanted = {str(item).strip() for item in operation_ids if str(item).strip()}
    for raw in rows:
        extra = raw.get("extra") or {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {}
        aliases = {
            str(alias or "").strip()
            for alias in (extra.get("candidate_ids") or extra.get("aliases") or [])
            if str(alias or "").strip()
        }
        if wanted & aliases:
            policy = str(raw.get("billing_policy") or "").strip()
            return policy or None
    return None


def pg_get_by_alias(session: Any, tenant_id: str, tokens: set[str]) -> PendingSettlement | None:
    wanted = {str(item).strip() for item in tokens if str(item).strip()}
    if not tenant_id or not wanted:
        return None
    stmt = text(
        "SELECT settlement_id, tenant_id, reservation_id, operation_id, billing_policy, state, "
        "created_at, updated_at, attempts, send_status, provider_message_id, channel, reason, extra "
        "FROM customer_ai_pending_settlements "
        "WHERE tenant_id = :tid AND (operation_id IN :ops OR reservation_id IN :ops) "
        "ORDER BY settlement_id LIMIT 1"
    ).bindparams(bindparam("ops", expanding=True))
    row = session.execute(stmt, {"tid": tenant_id, "ops": tuple(wanted)}).mappings().first()
    if row:
        return _row(dict(row))
    rows = (
        session.execute(
            text(
                "SELECT settlement_id, tenant_id, reservation_id, operation_id, billing_policy, state, "
                "created_at, updated_at, attempts, send_status, provider_message_id, channel, reason, extra "
                "FROM customer_ai_pending_settlements WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
        .mappings()
        .all()
    )
    for raw in rows:
        extra = raw.get("extra") or {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {}
        aliases = {
            str(alias or "").strip()
            for alias in (extra.get("candidate_ids") or extra.get("aliases") or [])
            if str(alias or "").strip()
        }
        if wanted & aliases:
            return _row(dict(raw))
    return None


def pg_get_by_reservation(session: Any, tenant_id: str, reservation_id: str) -> PendingSettlement | None:
    if not tenant_id or not reservation_id:
        return None
    row = (
        session.execute(
            text(
                "SELECT settlement_id, tenant_id, reservation_id, operation_id, billing_policy, state, "
                "created_at, updated_at, attempts, send_status, provider_message_id, channel, reason, extra "
                "FROM customer_ai_pending_settlements WHERE tenant_id = :tid AND reservation_id = :rid "
                "ORDER BY settlement_id LIMIT 1"
            ),
            {"tid": tenant_id, "rid": reservation_id},
        )
        .mappings()
        .first()
    )
    return _row(dict(row)) if row else None


def pg_get(session: Any, settlement_id: str) -> PendingSettlement | None:
    row = (
        session.execute(
            text(
                "SELECT settlement_id, tenant_id, reservation_id, operation_id, billing_policy, state, "
                "created_at, updated_at, attempts, send_status, provider_message_id, channel, reason, extra "
                "FROM customer_ai_pending_settlements WHERE settlement_id = :sid"
            ),
            {"sid": settlement_id},
        )
        .mappings()
        .first()
    )
    return _row(dict(row)) if row else None
