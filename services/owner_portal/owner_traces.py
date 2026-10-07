"""Async-safe message traces for the owner portal. Writes happen off the reply path."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

_SECRET_PARTS = ("api_key", "authorization", "password", "secret", "bearer", "token")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if any(part in str(key).lower() for part in _SECRET_PARTS):
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = _redact(item)
        return cleaned
    if isinstance(value, list):
        return [_redact(item) for item in value[:40]]
    if isinstance(value, str) and len(value) > 8000:
        return value[:8000]
    return value


def record_trace(payload: dict[str, Any]) -> None:
    """Schedule a trace write. Failures never affect the reply."""
    threading.Thread(target=_write, args=(_redact(dict(payload)),), daemon=True).start()


def _write(payload: dict[str, Any]) -> None:
    from db.session import whatsapp_session

    trace_id = str(payload.get("id") or uuid.uuid4().hex)
    try:
        with whatsapp_session(require=False) as session:
            session.execute(
                text(
                    """
                    INSERT INTO owner_message_traces
                      (id, tenant_id, brain, channel, created_at, has_error, tokens_in, tokens_out, cost_usd, payload)
                    VALUES
                      (:id, :tenant_id, :brain, :channel, :created_at, :has_error, :tokens_in, :tokens_out, :cost_usd, :payload)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "id": trace_id,
                    "tenant_id": str(payload.get("tenant_id") or ""),
                    "brain": str(payload.get("brain") or ""),
                    "channel": str(payload.get("channel") or ""),
                    "created_at": str(payload.get("created_at") or datetime.now(UTC).isoformat()),
                    "has_error": 1 if payload.get("error") else 0,
                    "tokens_in": int(payload.get("tokens_in") or 0),
                    "tokens_out": int(payload.get("tokens_out") or 0),
                    "cost_usd": float(payload.get("cost_usd") or 0),
                    "payload": json.dumps(payload, default=str),
                },
            )
    except Exception:
        return


def list_traces(
    *,
    tenant_id: str = "",
    brain: str = "",
    channel: str = "",
    has_error: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    from db.session import whatsapp_session

    clauses = ["1=1"]
    params: dict[str, Any] = {"limit": max(1, min(limit, 200)), "offset": max(0, offset)}
    if tenant_id:
        clauses.append("tenant_id = :tenant_id")
        params["tenant_id"] = tenant_id
    if brain:
        clauses.append("brain = :brain")
        params["brain"] = brain
    if channel:
        clauses.append("channel = :channel")
        params["channel"] = channel
    if has_error is True:
        clauses.append("has_error = 1")
    elif has_error is False:
        clauses.append("has_error = 0")
    where = " AND ".join(clauses)
    try:
        with whatsapp_session(require=False) as session:
            rows = session.execute(
                text(
                    f"""
                    SELECT id, tenant_id, brain, channel, created_at, has_error, tokens_in, tokens_out, cost_usd, payload
                    FROM owner_message_traces
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).all()
    except Exception:
        return []
    out = []
    for row in rows:
        try:
            body = json.loads(row[9] or "{}")
        except Exception:
            body = {}
        out.append(
            {
                "id": row[0],
                "tenant_id": row[1],
                "brain": row[2],
                "channel": row[3],
                "created_at": row[4],
                "has_error": bool(row[5]),
                "tokens_in": row[6],
                "tokens_out": row[7],
                "cost_usd": row[8],
                "payload": body,
            }
        )
    return out


def get_trace(trace_id: str) -> dict[str, Any] | None:
    from db.session import whatsapp_session

    try:
        with whatsapp_session(require=False) as session:
            row = session.execute(
                text("SELECT payload FROM owner_message_traces WHERE id = :id"),
                {"id": trace_id},
            ).first()
    except Exception:
        return None
    if row is None:
        return None
    try:
        body = json.loads(row[0] or "{}")
    except Exception:
        body = {}
    body["id"] = trace_id
    return body
