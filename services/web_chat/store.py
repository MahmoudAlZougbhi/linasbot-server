"""File-backed tenant Web Chat widget config and visitor sessions."""

from __future__ import annotations

import json
import secrets
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from services.web_chat.appearance import normalize_appearance, normalize_integration_mode
from services.web_chat.config_models import (
    WebChatInstallation,
    WebChatWidgetConfig,
    config_from_raw,
    config_to_raw,
)
from services.web_chat.domain import normalize_site_url, origin_allowed_for_site
from storage.persistent_storage import _DATA_ROOT


@dataclass
class WebChatMessage:
    id: str
    role: str
    content: str
    created_at: float


@dataclass
class WebChatVisitorSession:
    id: str
    tenant_id: str
    widget_key: str
    created_at: float
    updated_at: float
    messages: list[WebChatMessage] = field(default_factory=list)
    pending_assistant: list[WebChatMessage] = field(default_factory=list)


class WebChatStore:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "web_chat")
        self._tenants = self._root / "tenants"
        self._visitors = self._root / "visitors"
        self._tenants.mkdir(parents=True, exist_ok=True)
        self._visitors.mkdir(parents=True, exist_ok=True)

    def _tenant_path(self, tenant_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_id)[:80]
        return self._tenants / f"{safe}.json"

    def _visitor_path(self, session_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)[:80]
        return self._visitors / f"{safe}.json"

    def _load_widget(self, tenant_id: str) -> WebChatWidgetConfig | None:
        path = self._tenant_path(tenant_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        return config_from_raw(tenant_id, raw)

    def _save_widget(self, config: WebChatWidgetConfig) -> None:
        payload = config_to_raw(config)
        self._tenant_path(config.tenant_id).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_visitor(self, session_id: str) -> WebChatVisitorSession | None:
        path = self._visitor_path(session_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        def _msgs(key: str) -> list[WebChatMessage]:
            out: list[WebChatMessage] = []
            for m in raw.get(key) or []:
                if not isinstance(m, dict):
                    continue
                out.append(
                    WebChatMessage(
                        id=str(m.get("id") or uuid.uuid4().hex),
                        role=str(m.get("role") or "assistant"),
                        content=str(m.get("content") or ""),
                        created_at=float(m.get("created_at") or time.time()),
                    )
                )
            return out

        return WebChatVisitorSession(
            id=str(raw.get("id") or session_id),
            tenant_id=str(raw.get("tenant_id") or ""),
            widget_key=str(raw.get("widget_key") or ""),
            created_at=float(raw.get("created_at") or time.time()),
            updated_at=float(raw.get("updated_at") or time.time()),
            messages=_msgs("messages"),
            pending_assistant=_msgs("pending_assistant"),
        )

    def _save_visitor(self, session: WebChatVisitorSession) -> None:
        payload: dict[str, Any] = {
            "id": session.id,
            "tenant_id": session.tenant_id,
            "widget_key": session.widget_key,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "messages": [asdict(m) for m in session.messages],
            "pending_assistant": [asdict(m) for m in session.pending_assistant],
        }
        self._visitor_path(session.id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def get_widget_by_key(self, widget_key: str) -> WebChatWidgetConfig | None:
        key = (widget_key or "").strip()
        if not key:
            return None
        with self._lock:
            for path in self._tenants.glob("*.json"):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if str(raw.get("widget_key") or "") == key:
                    return self._load_widget(str(raw.get("tenant_id") or ""))
        return None

    def get_or_create_widget(self, tenant_id: str) -> WebChatWidgetConfig:
        tid = (tenant_id or "").strip().lower()
        if not tid:
            raise ValueError("tenant_id required")
        with self._lock:
            existing = self._load_widget(tid)
            if existing is not None:
                return existing
            now = time.time()
            config = WebChatWidgetConfig(
                tenant_id=tid,
                widget_key=secrets.token_urlsafe(24),
                site_url="",
                enabled=False,
                created_at=now,
                updated_at=now,
            )
            self._save_widget(config)
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
        new_site = normalize_site_url(site_url) if site_url is not None else config.site_url
        new_enabled = config.enabled if enabled is None else bool(enabled)
        new_mode = (
            normalize_integration_mode(integration_mode) if integration_mode is not None else config.integration_mode
        )
        new_appearance = normalize_appearance(appearance) if appearance is not None else config.appearance
        updated = WebChatWidgetConfig(
            tenant_id=config.tenant_id,
            widget_key=config.widget_key,
            site_url=new_site,
            enabled=new_enabled,
            created_at=config.created_at,
            updated_at=now,
            integration_mode=new_mode,
            appearance=new_appearance,
            installation=config.installation,
        )
        with self._lock:
            self._save_widget(updated)
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
        with self._lock:
            self._save_widget(updated)
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
        with self._lock:
            self._save_widget(updated)
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
    ) -> WebChatVisitorSession:
        sid = (session_id or "").strip()
        if not sid or len(sid) < 8 or len(sid) > 80:
            raise ValueError("invalid visitor_session_id")
        with self._lock:
            existing = self._load_visitor(sid)
            if existing is not None:
                return existing
            now = time.time()
            session = WebChatVisitorSession(
                id=sid,
                tenant_id=widget.tenant_id,
                widget_key=widget.widget_key,
                created_at=now,
                updated_at=now,
                messages=[
                    WebChatMessage(
                        id=uuid.uuid4().hex,
                        role="assistant",
                        content=greeting,
                        created_at=now,
                    )
                ],
            )
            self._save_visitor(session)
            return session

    def get_visitor(self, session_id: str) -> WebChatVisitorSession | None:
        with self._lock:
            return self._load_visitor(session_id)

    def append_turn(
        self,
        session_id: str,
        *,
        user_text: str,
        assistant_text: str,
    ) -> WebChatVisitorSession:
        with self._lock:
            session = self._load_visitor(session_id)
            if session is None:
                raise KeyError("session not found")
            now = time.time()
            session.messages.append(WebChatMessage(id=uuid.uuid4().hex, role="user", content=user_text, created_at=now))
            session.messages.append(
                WebChatMessage(
                    id=uuid.uuid4().hex,
                    role="assistant",
                    content=assistant_text,
                    created_at=now + 0.001,
                )
            )
            session.pending_assistant.clear()
            session.updated_at = now
            self._save_visitor(session)
            return session

    def queue_assistant_message(self, session_id: str, content: str) -> None:
        with self._lock:
            session = self._load_visitor(session_id)
            if session is None:
                raise KeyError("session not found")
            now = time.time()
            session.pending_assistant.append(
                WebChatMessage(id=uuid.uuid4().hex, role="assistant", content=content, created_at=now)
            )
            session.updated_at = now
            self._save_visitor(session)

    def drain_pending_assistant(self, session_id: str) -> list[WebChatMessage]:
        with self._lock:
            session = self._load_visitor(session_id)
            if session is None:
                return []
            pending = list(session.pending_assistant)
            if not pending:
                return []
            now = time.time()
            session.messages.extend(pending)
            session.pending_assistant.clear()
            session.updated_at = now
            self._save_visitor(session)
            return pending


web_chat_store = WebChatStore()
