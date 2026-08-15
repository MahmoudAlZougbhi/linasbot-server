"""Production PostgreSQL-backed Web Chat store (canonical SoT)."""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.web_chat.appearance import normalize_appearance, normalize_integration_mode
from services.web_chat.config_models import (
    WebChatInstallation,
    WebChatWidgetConfig,
    config_from_raw,
    config_to_raw,
)
from services.web_chat.domain import normalize_site_url, origin_allowed_for_site
from services.web_chat.ha_repository import (
    HaMessage,
    HaVisitorSession,
    WebChatHaRepository,
    WebChatHaUnavailable,
    web_chat_ha_repository,
    with_ha_session,
)
from services.web_chat.pg_models import WebChatWidgetRow
from services.web_chat.store_types import WebChatMessage, WebChatVisitorSession


def _msg_from_ha(msg: HaMessage) -> WebChatMessage:
    return WebChatMessage(id=msg.id, role=msg.role, content=msg.content, created_at=msg.created_at)


def _session_from_ha(ha: HaVisitorSession) -> WebChatVisitorSession:
    return WebChatVisitorSession(
        id=ha.id,
        tenant_id=ha.tenant_id,
        widget_key=ha.widget_key,
        created_at=ha.created_at,
        updated_at=ha.updated_at,
        authority_hash=ha.authority_hash,
        messages=[_msg_from_ha(m) for m in ha.messages],
        pending_assistant=[_msg_from_ha(m) for m in ha.pending_assistant],
    )


def _widget_from_row(row: WebChatWidgetRow) -> WebChatWidgetConfig:
    raw = dict(row.config or {})
    raw.setdefault("tenant_id", row.tenant_id)
    raw.setdefault("widget_key", row.widget_key)
    return config_from_raw(row.tenant_id, raw)


def _save_widget_row(session: Session, config: WebChatWidgetConfig) -> WebChatWidgetRow:
    row = session.scalars(select(WebChatWidgetRow).where(WebChatWidgetRow.tenant_id == config.tenant_id)).first()
    payload = config_to_raw(config)
    now = datetime.now(UTC)
    if row is None:
        row = WebChatWidgetRow(
            tenant_id=config.tenant_id,
            widget_key=config.widget_key,
            config=payload,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.widget_key = config.widget_key
        row.config = payload
        row.updated_at = now
    session.flush()
    return row


class WebChatPgStore:
    """Canonical HA store; fails closed when PostgreSQL or schema is unavailable."""

    def __init__(self, *, ha_repo: WebChatHaRepository | None = None) -> None:
        self._ha = ha_repo or web_chat_ha_repository

    def _validate_session_id(self, session_id: str) -> str:
        sid = (session_id or "").strip()
        if not sid or len(sid) < 8 or len(sid) > 80:
            raise ValueError("invalid visitor_session_id")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)
        if safe != sid:
            raise ValueError("invalid visitor_session_id")
        return sid

    def get_widget_by_key(self, widget_key: str) -> WebChatWidgetConfig | None:
        key = (widget_key or "").strip()
        if not key:
            return None
        with with_ha_session() as db:
            row = db.scalars(select(WebChatWidgetRow).where(WebChatWidgetRow.widget_key == key)).first()
            return _widget_from_row(row) if row is not None else None

    def get_or_create_widget(self, tenant_id: str) -> WebChatWidgetConfig:
        tid = (tenant_id or "").strip().lower()
        if not tid:
            raise ValueError("tenant_id required")
        with with_ha_session() as db:
            row = db.scalars(select(WebChatWidgetRow).where(WebChatWidgetRow.tenant_id == tid)).first()
            if row is not None:
                return _widget_from_row(row)
            now = time.time()
            config = WebChatWidgetConfig(
                tenant_id=tid,
                widget_key=secrets.token_urlsafe(24),
                site_url="",
                enabled=False,
                created_at=now,
                updated_at=now,
            )
            _save_widget_row(db, config)
            return config

    def update_widget(
        self,
        tenant_id: str,
        *,
        site_url: str | None = None,
        enabled: bool | None = None,
        integration_mode: str | None = None,
        appearance: dict[str, Any] | None = None,
    ) -> WebChatWidgetConfig:
        config = self.get_or_create_widget(tenant_id)
        now = time.time()
        updated = WebChatWidgetConfig(
            tenant_id=config.tenant_id,
            widget_key=config.widget_key,
            site_url=normalize_site_url(site_url) if site_url is not None else config.site_url,
            enabled=config.enabled if enabled is None else bool(enabled),
            created_at=config.created_at,
            updated_at=now,
            integration_mode=(
                normalize_integration_mode(integration_mode)
                if integration_mode is not None
                else config.integration_mode
            ),
            appearance=normalize_appearance(appearance) if appearance is not None else config.appearance,
            installation=config.installation,
        )
        with with_ha_session() as db:
            _save_widget_row(db, updated)
        return updated

    def rotate_widget_key(self, tenant_id: str) -> WebChatWidgetConfig:
        config = self.get_or_create_widget(tenant_id)
        now = time.time()
        updated = WebChatWidgetConfig(
            tenant_id=config.tenant_id,
            widget_key=secrets.token_urlsafe(24),
            site_url=config.site_url,
            enabled=config.enabled,
            created_at=config.created_at,
            updated_at=now,
            integration_mode=config.integration_mode,
            appearance=config.appearance,
            installation=config.installation,
        )
        with with_ha_session() as db:
            _save_widget_row(db, updated)
        return updated

    def record_installation_heartbeat(
        self,
        widget: WebChatWidgetConfig,
        *,
        origin: str | None,
    ) -> WebChatWidgetConfig:
        now = time.time()
        updated = WebChatWidgetConfig(
            tenant_id=widget.tenant_id,
            widget_key=widget.widget_key,
            site_url=widget.site_url,
            enabled=widget.enabled,
            created_at=widget.created_at,
            updated_at=now,
            integration_mode=widget.integration_mode,
            appearance=widget.appearance,
            installation=WebChatInstallation(
                last_seen_at=now,
                last_origin=str(origin or "").strip()[:500],
            ),
        )
        with with_ha_session() as db:
            _save_widget_row(db, updated)
        return updated

    def origin_allowed_for_widget(self, widget: WebChatWidgetConfig, origin: str | None) -> bool:
        if not widget.site_url:
            return False
        return origin_allowed_for_site(widget.site_url, origin)

    def get_or_create_visitor(
        self,
        *,
        session_id: str,
        widget: WebChatWidgetConfig,
        greeting: str,
        authority_hash: str = "",
    ) -> WebChatVisitorSession:
        sid = self._validate_session_id(session_id)
        auth = (authority_hash or "").strip()
        if not auth:
            raise WebChatHaUnavailable("Session authority hash required for HA visitor sessions.")
        with with_ha_session() as db:
            existing = self._ha.get_session(db, sid)
            if existing is not None:
                return _session_from_ha(existing)
            created = self._ha.create_session(
                db,
                session_id=sid,
                tenant_id=widget.tenant_id,
                widget_key=widget.widget_key,
                authority_hash=auth,
                greeting=greeting,
            )
            return _session_from_ha(created)

    def get_visitor(self, session_id: str) -> WebChatVisitorSession | None:
        try:
            self._validate_session_id(session_id)
        except ValueError:
            return None
        with with_ha_session() as db:
            loaded = self._ha.get_session(db, session_id)
            return _session_from_ha(loaded) if loaded is not None else None

    def append_turn(
        self,
        session_id: str,
        *,
        user_text: str,
        assistant_text: str,
        turn_key: str | None = None,
    ) -> WebChatVisitorSession:
        with with_ha_session() as db:
            loaded = self._ha.get_session(db, session_id)
            if loaded is None:
                raise KeyError("session not found")
            self._ha.append_turn(
                db,
                session_id=session_id,
                tenant_id=loaded.tenant_id,
                user_text=user_text,
                assistant_text=assistant_text,
                turn_key=turn_key,
            )
            refreshed = self._ha.get_session(db, session_id)
            if refreshed is None:
                raise WebChatHaUnavailable("Visitor session missing after append_turn.")
            return _session_from_ha(refreshed)

    def has_assistant_delivery(self, session_id: str, idempotency_key: str) -> bool:
        key = (idempotency_key or "").strip()
        if not key:
            return False
        with with_ha_session() as db:
            loaded = self._ha.get_session(db, session_id)
            if loaded is None:
                return False
            for message in (*loaded.pending_assistant, *loaded.messages):
                if message.id == key and message.role == "assistant":
                    return True
            return self._ha.has_idempotency(db, tenant_id=loaded.tenant_id, idempotency_key=key)

    def queue_assistant_message(
        self,
        session_id: str,
        content: str,
        *,
        idempotency_key: str | None = None,
    ) -> bool:
        msg_id = (idempotency_key or "").strip() or uuid.uuid4().hex
        with with_ha_session() as db:
            loaded = self._ha.get_session(db, session_id)
            if loaded is None:
                raise KeyError("session not found")
            if idempotency_key:
                if self._ha.has_idempotency(db, tenant_id=loaded.tenant_id, idempotency_key=idempotency_key):
                    return False
                claimed = self._ha.claim_idempotency(
                    db,
                    tenant_id=loaded.tenant_id,
                    session_id=session_id,
                    idempotency_key=idempotency_key,
                    message_id=msg_id,
                )
                if not claimed:
                    return False
            queued = self._ha.queue_assistant(
                db,
                session_id=session_id,
                tenant_id=loaded.tenant_id,
                content=content,
                message_id=msg_id,
            )
            return queued

    def ack_assistant_messages(self, session_id: str, *, message_ids: list[str]) -> int:
        ids = [str(mid).strip() for mid in (message_ids or []) if str(mid).strip()]
        if not ids:
            return 0
        with with_ha_session() as db:
            return self._ha.ack_messages(db, session_id=session_id, message_ids=ids)

    def list_pending_since_cursor(
        self,
        session_id: str,
        *,
        cursor: str | None = None,
    ) -> tuple[list[WebChatMessage], str | None]:
        with with_ha_session() as db:
            pending, next_cursor = self._ha.list_since_cursor(db, session_id=session_id, cursor=cursor)
        return [_msg_from_ha(m) for m in pending], next_cursor

    def drain_pending_assistant(self, session_id: str) -> list[WebChatMessage]:
        with with_ha_session() as db:
            loaded = self._ha.get_session(db, session_id)
            if loaded is None or not loaded.pending_assistant:
                return []
            ids = [m.id for m in loaded.pending_assistant]
            self._ha.ack_messages(db, session_id=session_id, message_ids=ids)
            return [_msg_from_ha(m) for m in loaded.pending_assistant]
