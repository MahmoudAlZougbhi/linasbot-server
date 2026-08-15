"""PostgreSQL-backed HA repository for Website Chat."""

from __future__ import annotations

import time
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.session import whatsapp_db_configured, whatsapp_session
from services.web_chat.pg_models import (
    WebChatDeliveryIdempotencyRow,
    WebChatMessageRow,
    WebChatVisitorSessionRow,
)


class WebChatHaUnavailable(RuntimeError):
    code = "WEB_CHAT_HA_UNAVAILABLE"


@dataclass
class HaMessage:
    id: str
    role: str
    content: str
    created_at: float
    acked: bool = False


@dataclass
class HaVisitorSession:
    id: str
    tenant_id: str
    widget_key: str
    authority_hash: str
    created_at: float
    updated_at: float
    messages: list[HaMessage]
    pending_assistant: list[HaMessage]


def _now_ts() -> float:
    return time.time()


def _row_to_msg(row: WebChatMessageRow) -> HaMessage:
    created = row.created_at.timestamp() if row.created_at else _now_ts()
    return HaMessage(
        id=row.message_id,
        role=row.role,
        content=row.content,
        created_at=created,
        acked=row.acked_at is not None,
    )


class WebChatHaRepository:
    def create_session(
        self,
        session: Session,
        *,
        session_id: str,
        tenant_id: str,
        widget_key: str,
        authority_hash: str,
        greeting: str,
    ) -> HaVisitorSession:
        now = datetime.now(UTC)
        row = WebChatVisitorSessionRow(
            session_id=session_id,
            tenant_id=tenant_id,
            widget_key=widget_key,
            authority_hash=authority_hash,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        msg = WebChatMessageRow(
            session_id=session_id,
            tenant_id=tenant_id,
            message_id=uuid.uuid4().hex,
            role="assistant",
            content=greeting,
            created_at=now,
            acked_at=now,
            meta={"kind": "greeting"},
        )
        session.add(msg)
        session.flush()
        loaded = self._load(session, session_id)
        if loaded is None:
            raise WebChatHaUnavailable("Visitor session could not be loaded after create.")
        return loaded

    def get_session(self, session: Session, session_id: str) -> HaVisitorSession | None:
        return self._load(session, session_id)

    def _load(self, session: Session, session_id: str) -> HaVisitorSession | None:
        sess_row = session.scalars(
            select(WebChatVisitorSessionRow).where(WebChatVisitorSessionRow.session_id == session_id)
        ).first()
        if sess_row is None:
            return None
        msg_rows = session.scalars(
            select(WebChatMessageRow)
            .where(WebChatMessageRow.session_id == session_id)
            .order_by(WebChatMessageRow.created_at.asc())
        ).all()
        messages: list[HaMessage] = []
        pending: list[HaMessage] = []
        for row in msg_rows:
            msg = _row_to_msg(row)
            if row.role == "assistant" and row.acked_at is None:
                pending.append(msg)
            else:
                messages.append(msg)
        created = sess_row.created_at.timestamp() if sess_row.created_at else _now_ts()
        updated = sess_row.updated_at.timestamp() if sess_row.updated_at else created
        return HaVisitorSession(
            id=sess_row.session_id,
            tenant_id=sess_row.tenant_id,
            widget_key=sess_row.widget_key,
            authority_hash=sess_row.authority_hash,
            created_at=created,
            updated_at=updated,
            messages=messages,
            pending_assistant=pending,
        )

    def claim_idempotency(
        self,
        session: Session,
        *,
        tenant_id: str,
        session_id: str,
        idempotency_key: str,
        message_id: str,
    ) -> bool:
        """Return True when claim created; False when duplicate."""
        row = WebChatDeliveryIdempotencyRow(
            tenant_id=tenant_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
            message_id=message_id,
        )
        session.add(row)
        try:
            session.flush()
            return True
        except IntegrityError:
            session.rollback()
            return False

    def has_idempotency(self, session: Session, *, tenant_id: str, idempotency_key: str) -> bool:
        return (
            session.scalars(
                select(WebChatDeliveryIdempotencyRow).where(
                    WebChatDeliveryIdempotencyRow.tenant_id == tenant_id,
                    WebChatDeliveryIdempotencyRow.idempotency_key == idempotency_key,
                )
            ).first()
            is not None
        )

    def append_turn(
        self,
        session: Session,
        *,
        session_id: str,
        tenant_id: str,
        user_text: str,
        assistant_text: str,
        turn_key: str | None = None,
    ) -> None:
        key = str(turn_key or "").strip()
        user_message_id = f"{key}:user" if key else uuid.uuid4().hex
        assistant_message_id = f"{key}:assistant" if key else uuid.uuid4().hex
        if key:
            session.scalars(
                select(WebChatVisitorSessionRow)
                .where(WebChatVisitorSessionRow.session_id == session_id)
                .with_for_update()
            ).first()
            existing = session.scalars(
                select(WebChatMessageRow).where(
                    WebChatMessageRow.session_id == session_id,
                    WebChatMessageRow.message_id.in_([user_message_id, assistant_message_id]),
                )
            ).all()
            if len(existing) >= 2:
                return
        now = datetime.now(UTC)
        try:
            session.add(
                WebChatMessageRow(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    message_id=user_message_id,
                    role="user",
                    content=user_text,
                    created_at=now,
                    acked_at=now,
                )
            )
            session.add(
                WebChatMessageRow(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    message_id=assistant_message_id,
                    role="assistant",
                    content=assistant_text,
                    created_at=now,
                    acked_at=now,
                )
            )
            session.flush()
        except IntegrityError:
            session.rollback()
            return
        sess = session.scalars(
            select(WebChatVisitorSessionRow).where(WebChatVisitorSessionRow.session_id == session_id)
        ).first()
        if sess is not None:
            sess.updated_at = now

    def queue_assistant(
        self,
        session: Session,
        *,
        session_id: str,
        tenant_id: str,
        content: str,
        message_id: str,
    ) -> bool:
        exists = session.scalars(
            select(WebChatMessageRow).where(
                WebChatMessageRow.session_id == session_id,
                WebChatMessageRow.message_id == message_id,
            )
        ).first()
        if exists is not None:
            return False
        now = datetime.now(UTC)
        session.add(
            WebChatMessageRow(
                session_id=session_id,
                tenant_id=tenant_id,
                message_id=message_id,
                role="assistant",
                content=content,
                created_at=now,
                acked_at=None,
            )
        )
        sess = session.scalars(
            select(WebChatVisitorSessionRow).where(WebChatVisitorSessionRow.session_id == session_id)
        ).first()
        if sess is not None:
            sess.updated_at = now
        return True

    def list_since_cursor(
        self,
        session: Session,
        *,
        session_id: str,
        cursor: str | None,
    ) -> tuple[list[HaMessage], str | None]:
        rows = session.scalars(
            select(WebChatMessageRow)
            .where(WebChatMessageRow.session_id == session_id)
            .order_by(WebChatMessageRow.created_at.asc())
        ).all()
        after = False
        if not cursor:
            after = True
        out: list[HaMessage] = []
        last_id: str | None = cursor
        for row in rows:
            if not after:
                if row.message_id == cursor:
                    after = True
                continue
            if row.role == "assistant" and row.acked_at is None:
                out.append(_row_to_msg(row))
                last_id = row.message_id
        return out, last_id

    def ack_messages(self, session: Session, *, session_id: str, message_ids: list[str]) -> int:
        if not message_ids:
            return 0
        now = datetime.now(UTC)
        count = 0
        rows = session.scalars(
            select(WebChatMessageRow).where(
                WebChatMessageRow.session_id == session_id,
                WebChatMessageRow.message_id.in_(message_ids),
            )
        ).all()
        for row in rows:
            if row.acked_at is None:
                row.acked_at = now
                count += 1
        return count


web_chat_ha_repository = WebChatHaRepository()


def with_ha_session() -> AbstractContextManager[Any]:
    if not whatsapp_db_configured():
        raise WebChatHaUnavailable("PostgreSQL required for Website Chat HA store.")
    return whatsapp_session()
