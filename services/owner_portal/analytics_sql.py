"""Owner overview counts from Postgres. Avoids loading every user document."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text

_USER_PARENT = "artifacts/linas-ai-bot-backend/dashboard_users"
_ACTIVE = ("active", "trial", "grace")


def _stamp(expr: str) -> str:
    """ISO text or unix seconds stored in the user JSON."""
    return f"""
      CASE
        WHEN {expr} ~ '^[0-9]{{4}}-' THEN {expr}::timestamptz
        WHEN {expr} ~ '^[0-9]+(\\.[0-9]+)?$' THEN to_timestamp({expr}::double precision)
        ELSE NULL
      END
    """


def load_overview(start: datetime, end: datetime) -> dict[str, Any] | None:
    from db.session import whatsapp_session

    created = _stamp("COALESCE(data_json::jsonb->>'createdAt', data_json::jsonb->>'created_at', '')")
    login = _stamp("COALESCE(data_json::jsonb->>'lastLogin', data_json::jsonb->>'last_login', '')")
    try:
        with whatsapp_session(require=True) as session:
            new_users, live_users = session.execute(
                text(
                    f"""
                    SELECT
                      count(*) FILTER (WHERE created_at >= :start AND created_at < :end),
                      count(*) FILTER (WHERE last_login >= :start AND last_login < :end)
                    FROM (
                      SELECT {created} AS created_at, {login} AS last_login
                      FROM linas_documents
                      WHERE parent = :parent
                    ) users
                    """
                ),
                {"start": start, "end": end, "parent": _USER_PARENT},
            ).one()
            subscribers = session.execute(
                text(
                    """
                    SELECT count(*) FROM tenant_entitlements
                    WHERE status IN ('active', 'trial', 'grace')
                    """
                )
            ).scalar()
            messages = session.execute(
                text(
                    """
                    WITH active AS (
                      SELECT tenant_id FROM tenant_entitlements
                      WHERE status IN ('active', 'trial', 'grace')
                    ),
                    live AS (
                      SELECT COALESCE(SUM(l.remaining), 0) AS total
                      FROM customer_ai_message_lots l
                      JOIN active a ON a.tenant_id = l.tenant_id
                      WHERE l.expires = false
                         OR l.period_id = to_char((now() AT TIME ZONE 'utc'), 'YYYY-MM')
                    ),
                    reserved AS (
                      SELECT COALESCE(SUM(r.units), 0) AS total
                      FROM customer_ai_message_reservations r
                      JOIN active a ON a.tenant_id = r.tenant_id
                      WHERE r.status = 'reserved'
                    )
                    SELECT
                      live.total,
                      GREATEST(live.total - reserved.total, 0),
                      (SELECT COALESCE(SUM(available), 0) FROM credit_balances
                       WHERE tenant_id IN (SELECT tenant_id FROM active))
                    FROM live, reserved
                    """
                )
            ).one()
            plans = (
                session.execute(
                    text(
                        """
                    SELECT plan_id FROM tenant_entitlements
                    WHERE status IN ('active', 'trial', 'grace')
                    """
                    )
                )
                .scalars()
                .all()
            )
    except Exception:
        return None
    return {
        "new_users": int(new_users or 0),
        "live_users": int(live_users or 0),
        "subscribers": int(subscribers or 0),
        "credits_total": int(messages[0] or 0),
        "credits_used": int(messages[0] or 0) - int(messages[1] or 0),
        "credits_remaining": int(messages[1] or 0),
        "messages_total": int(messages[0] or 0),
        "messages_used": int(messages[0] or 0) - int(messages[1] or 0),
        "messages_remaining": int(messages[1] or 0),
        "historical_credit_remaining": int(messages[2] or 0),
        "plan_ids": [str(plan or "") for plan in plans],
        "active_statuses": list(_ACTIVE),
    }


def tenant_is_known(tenant_id: str) -> bool:
    tid = (tenant_id or "").strip()
    if not tid or tid == "__platform__":
        return False
    from db.session import whatsapp_session

    try:
        with whatsapp_session(require=True) as session:
            hit = session.execute(
                text(
                    """
                    SELECT 1 FROM tenant_entitlements WHERE tenant_id = :tid
                    UNION ALL
                    SELECT 1 FROM customer_ai_message_lots WHERE tenant_id = :tid
                    UNION ALL
                    SELECT 1 FROM linas_documents
                    WHERE parent = :parent
                      AND lower(COALESCE(data_json::jsonb->>'tenantId', data_json::jsonb->>'tenant_id', '')) = lower(:tid)
                    LIMIT 1
                    """
                ),
                {"tid": tid, "parent": _USER_PARENT},
            ).first()
    except Exception:
        return True
    return hit is not None
