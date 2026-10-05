"""Tenant-scoped chat threads and messages. Postgres is the only store."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from db.session import whatsapp_session
from services.live_chat.contracts import utc_now
from services.live_chat.tenant import normalize_live_chat_tenant_id, resolve_live_chat_tenant_id
from services.persistence.schema import ensure_schema


class ChatTenantRequired(ValueError):
    """A chat row or event without tenant_id is not stored."""


def _bucket(state: str) -> str:
    value = (state or "").strip()
    if value == "waiting_for_operator":
        return "waiting"
    if value == "assigned_to_operator":
        return "with_operator"
    if value in {"resolved", "archived"}:
        return "closed"
    return "bot_active"


def empty_counters() -> dict[str, int]:
    return {"all": 0, "waiting": 0, "with_operator": 0, "bot_active": 0, "closed": 0}


def _session():
    return whatsapp_session(require=True)


def _require_tenant(tenant_id: str) -> str:
    tid = normalize_live_chat_tenant_id(tenant_id)
    if not tid:
        raise ChatTenantRequired("tenant_id is required")
    return tid


def append_message(
    *,
    user_id: str,
    role: str,
    text_body: str,
    conversation_id: str | None = None,
    user_name: str | None = None,
    phone_number: str | None = None,
    metadata: dict | None = None,
    channel: str = "",
    conversation_state: str = "bot_active",
) -> dict[str, Any]:
    """Insert one message and update the inbox row. Duplicate message ids are ignored."""
    meta = dict(metadata or {})
    info = {"name": user_name or "", "phone_full": phone_number or "", "tenant_id": meta.get("tenant_id")}
    tid = resolve_live_chat_tenant_id(
        user_id=user_id,
        conversation_id=conversation_id,
        payload={"customer_info": info, "metadata": meta},
    )
    if not tid:
        raise ChatTenantRequired("tenant_id is required")
    conv = (conversation_id or "").strip() or str(uuid.uuid4())
    message_id = str(meta.get("message_id") or meta.get("source_message_id") or uuid.uuid4())
    sent_at = utc_now().isoformat()
    with _session() as session:
        ensure_schema(session)
        inserted = session.execute(
            text(
                """
                INSERT INTO linas_chat_messages
                    (tenant_id, conversation_id, message_id, role, body, sent_at, metadata_json)
                VALUES
                    (:tenant_id, :conversation_id, :message_id, :role, :body, :sent_at, :metadata_json)
                ON CONFLICT (tenant_id, conversation_id, message_id) DO NOTHING
                """
            ),
            {
                "tenant_id": tid,
                "conversation_id": conv,
                "message_id": message_id,
                "role": role,
                "body": text_body or "",
                "sent_at": sent_at,
                "metadata_json": json.dumps(meta, default=str),
            },
        )
        duplicate = inserted.rowcount == 0
        if not duplicate:
            _upsert_thread(
                session,
                tenant_id=tid,
                conversation_id=conv,
                user_id=user_id,
                role=role,
                text_body=text_body or "",
                sent_at=sent_at,
                user_name=user_name or "",
                phone_number=phone_number or "",
                channel=channel or str(meta.get("channel") or ""),
                conversation_state=conversation_state,
            )
    return {
        "tenant_id": tid,
        "conversation_id": conv,
        "message_id": message_id,
        "duplicate": duplicate,
        "sent_at": sent_at,
        "role": role,
        "text": text_body or "",
    }


def _upsert_thread(
    session: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    user_id: str,
    role: str,
    text_body: str,
    sent_at: str,
    user_name: str,
    phone_number: str,
    channel: str,
    conversation_state: str,
) -> None:
    existing = (
        session.execute(
            text(
                """
            SELECT unread_count, message_count FROM linas_chat_threads
            WHERE tenant_id = :tenant_id AND conversation_id = :conversation_id
            """
            ),
            {"tenant_id": tenant_id, "conversation_id": conversation_id},
        )
        .mappings()
        .first()
    )
    unread = int(existing["unread_count"]) if existing else 0
    count = int(existing["message_count"]) if existing else 0
    if role == "user":
        unread += 1
    elif role == "operator":
        unread = 0
    count += 1
    session.execute(
        text(
            """
            INSERT INTO linas_chat_threads (
                tenant_id, conversation_id, user_id, channel, conversation_state,
                last_message_at, last_message_text, user_name, user_phone,
                unread_count, message_count
            ) VALUES (
                :tenant_id, :conversation_id, :user_id, :channel, :conversation_state,
                :last_message_at, :last_message_text, :user_name, :user_phone,
                :unread_count, :message_count
            )
            ON CONFLICT (tenant_id, conversation_id) DO UPDATE SET
                user_id = excluded.user_id,
                channel = CASE WHEN excluded.channel = '' THEN linas_chat_threads.channel ELSE excluded.channel END,
                conversation_state = excluded.conversation_state,
                last_message_at = excluded.last_message_at,
                last_message_text = excluded.last_message_text,
                user_name = CASE WHEN excluded.user_name = '' THEN linas_chat_threads.user_name ELSE excluded.user_name END,
                user_phone = CASE WHEN excluded.user_phone = '' THEN linas_chat_threads.user_phone ELSE excluded.user_phone END,
                unread_count = excluded.unread_count,
                message_count = excluded.message_count
            """
        ),
        {
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "channel": channel,
            "conversation_state": conversation_state,
            "last_message_at": sent_at,
            "last_message_text": text_body[:500],
            "user_name": user_name,
            "user_phone": phone_number,
            "unread_count": unread,
            "message_count": count,
        },
    )


def counters_for_tenant(tenant_id: str) -> dict[str, int]:
    tid = _require_tenant(tenant_id)
    totals = {"all": 0, "waiting": 0, "with_operator": 0, "bot_active": 0, "closed": 0}
    with _session() as session:
        ensure_schema(session)
        rows = session.execute(
            text(
                """
                SELECT conversation_state, COUNT(*) AS n
                FROM linas_chat_threads
                WHERE tenant_id = :tenant_id
                GROUP BY conversation_state
                """
            ),
            {"tenant_id": tid},
        ).mappings()
        for row in rows:
            n = int(row["n"])
            totals["all"] += n
            totals[_bucket(str(row["conversation_state"]))] += n
    return totals


def list_inbox(
    tenant_id: str,
    *,
    limit: int = 30,
    cursor: str | None = None,
    search: str = "",
    states: list[str] | None = None,
    channel: str = "",
) -> dict[str, Any]:
    """One tenant, indexed order. No cross-tenant scan."""
    tid = _require_tenant(tenant_id)
    cap = max(1, min(int(limit), 100))
    stamp, conv = "", ""
    raw = (cursor or "").strip()
    if "|" in raw:
        stamp, conv = raw.split("|", 1)
    needle = (search or "").strip().lower()
    state_list = [str(item) for item in (states or []) if str(item).strip()]
    where = ["tenant_id = :tenant_id"]
    params: dict[str, Any] = {"tenant_id": tid, "limit": cap + 1}
    if stamp:
        where.append("(last_message_at < :stamp OR (last_message_at = :stamp AND conversation_id < :conv))")
        params["stamp"] = stamp
        params["conv"] = conv
    if needle:
        where.append("(lower(user_name) LIKE :needle OR lower(user_phone) LIKE :needle)")
        params["needle"] = f"%{needle}%"
    if state_list:
        names = []
        for index, state in enumerate(state_list):
            key = f"state_{index}"
            names.append(f":{key}")
            params[key] = state
        where.append(f"conversation_state IN ({', '.join(names)})")
    if channel:
        where.append("channel = :channel")
        params["channel"] = channel
    sql = f"""
        SELECT * FROM linas_chat_threads
        WHERE {" AND ".join(where)}
        ORDER BY last_message_at DESC, conversation_id DESC
        LIMIT :limit
    """
    with _session() as session:
        ensure_schema(session)
        rows = [dict(row) for row in session.execute(text(sql), params).mappings()]
    has_more = len(rows) > cap
    page = rows[:cap]
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = f"{last['last_message_at']}|{last['conversation_id']}"
    return {"threads": page, "has_more": has_more, "next_cursor": next_cursor}


def get_thread(tenant_id: str, conversation_id: str) -> dict[str, Any] | None:
    tid = _require_tenant(tenant_id)
    with _session() as session:
        ensure_schema(session)
        row = (
            session.execute(
                text(
                    """
                SELECT * FROM linas_chat_threads
                WHERE tenant_id = :tenant_id AND conversation_id = :conversation_id
                """
                ),
                {"tenant_id": tid, "conversation_id": conversation_id},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def list_messages(
    tenant_id: str,
    conversation_id: str,
    *,
    limit: int = 40,
    before: str | None = None,
) -> list[dict[str, Any]]:
    tid = _require_tenant(tenant_id)
    params: dict[str, Any] = {
        "tenant_id": tid,
        "conversation_id": conversation_id,
        "limit": max(1, min(int(limit), 100)),
    }
    extra = ""
    if before:
        extra = "AND sent_at < :before"
        params["before"] = before
    with _session() as session:
        ensure_schema(session)
        rows = session.execute(
            text(
                f"""
                SELECT * FROM linas_chat_messages
                WHERE tenant_id = :tenant_id AND conversation_id = :conversation_id
                {extra}
                ORDER BY sent_at DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings()
        return [dict(row) for row in rows]
