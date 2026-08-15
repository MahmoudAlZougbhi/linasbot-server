"""Server-issued session authority bound to tenant + widget."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

from services.web_chat.config_models import WebChatWidgetConfig

if TYPE_CHECKING:
    from services.web_chat.operation_fsm import VerifiedSessionSnapshot


class SessionAuthorityError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SessionAuthorityBundle:
    session_id: str
    authority_token: str
    authority_hash: str


def verified_session_snapshot(
    *,
    widget: WebChatWidgetConfig | None = None,
    tenant_id: str | None = None,
    widget_key: str | None = None,
    session_id: str,
    authority_hash: str,
) -> VerifiedSessionSnapshot:
    from services.web_chat.operation_fsm import VerifiedSessionSnapshot

    tid = (tenant_id or (widget.tenant_id if widget is not None else "")).strip().lower()
    wkey = (widget_key or (widget.widget_key if widget is not None else "")).strip()
    return VerifiedSessionSnapshot(
        tenant_id=tid,
        widget_key=wkey,
        session_id=str(session_id or "").strip(),
        authority_hash=str(authority_hash or "").strip(),
    )


def _hash_authority(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session_authority(*, widget: WebChatWidgetConfig) -> SessionAuthorityBundle:
    """Issue a fresh cryptographically random session bound to tenant + widget."""
    session_id = secrets.token_urlsafe(24)
    authority_token = secrets.token_urlsafe(32)
    return SessionAuthorityBundle(
        session_id=session_id,
        authority_token=authority_token,
        authority_hash=_hash_authority(authority_token),
    )


def hash_session_authority(token: str) -> str:
    return _hash_authority((token or "").strip())


def verify_session_binding(
    *,
    session_tenant_id: str,
    session_widget_key: str,
    authority_hash: str,
    widget: WebChatWidgetConfig,
    presented_authority: str,
) -> None:
    tid = (session_tenant_id or "").strip().lower()
    wkey = (session_widget_key or "").strip()
    if tid != widget.tenant_id.strip().lower() or wkey != widget.widget_key:
        raise SessionAuthorityError("SESSION_BOUNDARY", "Session does not belong to this widget.")
    token = (presented_authority or "").strip()
    if not token or _hash_authority(token) != (authority_hash or "").strip():
        raise SessionAuthorityError("SESSION_AUTHORITY_INVALID", "Invalid session authority.")
