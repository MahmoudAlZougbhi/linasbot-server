"""Index leftover-credit holds for known tenants only. Never invent tenant ids."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT

_LEFTOVER_OPS = frozenset(
    {
        "customer_ai_reply",
        "web_customer_reply",
        "whatsapp_customer_reply",
        "tiktok_customer_reply",
        "omnichannel_customer_reply",
        "omni",
        "whatsapp",
        "legacy_credits",
        "smart_followup",
        "whatsapp_smart_followup",
        "whatsapp_cloud",
        "tiktok",
    }
)
_LEFTOVER_TOKENS = ("customer_reply", "customer_ai", "followup", "leftover")


def leftover_op(operation_type: str) -> bool:
    name = (operation_type or "").strip().lower()
    if name in _LEFTOVER_OPS:
        return True
    return any(token in name for token in _LEFTOVER_TOKENS)


def leftover_closed(reservation_id: str, request_id: str, closed: set[str]) -> bool:
    """Capture/release may key the original request id or the reservation id."""
    rid = (reservation_id or "").strip()
    req = (request_id or "").strip()
    return bool((rid and rid in closed) or (req and req in closed))


def _iso(created_at: Any) -> str:
    if isinstance(created_at, str) and created_at.strip():
        return created_at
    try:
        return datetime.fromtimestamp(float(created_at or 0), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return datetime.now(UTC).isoformat()


def known_credit_tenant_ids() -> list[str]:
    ids: set[str] = set()
    try:
        from services.entitlements_service import entitlements_store

        ids.update(entitlements_store.list_tenant_ids())
    except Exception:
        pass
    try:
        from services.membership.message_ledger import known_ledger_tenant_ids

        ids.update(known_ledger_tenant_ids())
    except Exception:
        pass
    try:
        from services.membership.pending_settlement import known_settlement_tenant_ids

        ids.update(known_settlement_tenant_ids())
    except Exception:
        pass
    try:
        from services.billing_backend import billing_uses_postgres, require_billing_pg_session
        from services.credit_ledger_pg_store import list_reserve_tenant_ids

        if billing_uses_postgres():
            with require_billing_pg_session() as session:
                ids.update(list_reserve_tenant_ids(session))
    except Exception:
        pass
    try:
        from services.membership.credit_reservation_index import known_index_tenant_ids

        ids.update(known_index_tenant_ids())
    except Exception:
        pass
    try:
        from services.customer_ai.outbox import known_outbox_tenant_ids

        ids.update(known_outbox_tenant_ids())
    except Exception:
        pass
    root = Path(_DATA_ROOT) / "credit_ledger"
    if root.is_dir():
        for path in root.glob("*.balance.json"):
            ids.add(path.name.removesuffix(".balance.json"))
        for path in root.glob("*.jsonl"):
            ids.add(path.name.removesuffix(".jsonl"))
    for folder in ("pending_settlements", "credit_reservation_index"):
        extra = Path(_DATA_ROOT) / folder
        if not extra.is_dir():
            continue
        for path in extra.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            ids.add(str(data.get("tenant_id") or "").strip())
    return sorted(item for item in ids if item)


def _open_from_file(tenant_id: str) -> list[dict[str, str]]:
    path = Path(_DATA_ROOT) / "credit_ledger" / f"{tenant_id}.jsonl"
    if not path.is_file():
        return []
    reserved: dict[str, dict[str, Any]] = {}
    closed: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("tenant_id") or "") != tenant_id:
            continue
        op = str(row.get("op") or "")
        rid = str(row.get("id") or "")
        if op == "reserve" and rid:
            reserved[rid] = row
        if op in {"capture", "release"}:
            closed_id = str(row.get("request_id") or "").strip()
            if closed_id:
                closed.add(closed_id)
    out: list[dict[str, str]] = []
    for rid, row in reserved.items():
        if leftover_closed(rid, str(row.get("request_id") or ""), closed) or not leftover_op(
            str(row.get("operation_type") or "")
        ):
            continue
        out.append(
            {
                "reservation_id": rid,
                "request_id": str(row.get("request_id") or rid),
                "operation_type": str(row.get("operation_type") or "legacy_credits"),
                "created_at": _iso(row.get("created_at")),
            }
        )
    return out


def _open_from_pg(tenant_id: str) -> list[dict[str, str]] | None:
    try:
        from services.billing_backend import billing_uses_postgres

        if not billing_uses_postgres():
            return None
        from services.billing_backend import require_billing_pg_session
        from services.credit_ledger_pg_store import list_open_leftover_reservations

        with require_billing_pg_session() as session:
            return list_open_leftover_reservations(session, tenant_id)
    except Exception:
        return []


def _open_for_tenant(tenant_id: str) -> list[dict[str, str]]:
    pg_rows = _open_from_pg(tenant_id)
    if pg_rows is not None:
        return pg_rows
    return _open_from_file(tenant_id)


def seed_from_known_ledgers(*, limit: int = 50) -> int:
    from services.membership.credit_reservation_index import record_open

    cap = max(1, min(int(limit), 200))
    seeded = 0
    for tenant_id in known_credit_tenant_ids():
        rows = _open_for_tenant(tenant_id)
        for row in rows:
            record_open(
                tenant_id=tenant_id,
                reservation_id=row["reservation_id"],
                request_id=row["request_id"],
                operation_type=row["operation_type"],
                created_at=row["created_at"],
            )
            seeded += 1
            if seeded >= cap:
                return seeded
    return seeded
