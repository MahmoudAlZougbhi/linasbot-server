"""Durable visitor session tenant/widget binding for delivery authority."""

from __future__ import annotations

from dataclasses import dataclass

from services.web_chat.store import WebChatStoreBackend


class FollowUpSessionBoundaryError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DurableVisitorBinding:
    tenant_id: str
    widget_key: str
    session_id: str
    authority_hash: str


def resolve_durable_visitor_binding(
    *,
    store: WebChatStoreBackend,
    visitor_id: str,
    expected_tenant_id: str,
    expected_widget_key: str,
) -> DurableVisitorBinding:
    """Load PG/file visitor session and verify immutable tenant+widget binding."""
    sid = str(visitor_id or "").strip()
    if not sid:
        raise FollowUpSessionBoundaryError("missing_visitor", "Visitor session id is required.")
    visitor = store.get_visitor(sid)
    if visitor is None:
        raise FollowUpSessionBoundaryError("visitor_session_missing", "Visitor session not found.")
    tid = str(getattr(visitor, "tenant_id", "") or "").strip().lower()
    wkey = str(getattr(visitor, "widget_key", "") or "").strip()
    auth = str(getattr(visitor, "authority_hash", "") or "").strip()
    expected_tid = str(expected_tenant_id or "").strip().lower()
    expected_wkey = str(expected_widget_key or "").strip()
    if not tid or not wkey:
        raise FollowUpSessionBoundaryError("session_binding_incomplete", "Visitor session binding is incomplete.")
    if not auth:
        raise FollowUpSessionBoundaryError("session_authority_missing", "Visitor session authority is missing.")
    if tid != expected_tid:
        raise FollowUpSessionBoundaryError("cross_tenant_session", "Visitor session tenant mismatch.")
    if wkey != expected_wkey:
        raise FollowUpSessionBoundaryError("cross_widget_session", "Visitor session widget mismatch.")
    return DurableVisitorBinding(
        tenant_id=tid,
        widget_key=wkey,
        session_id=sid,
        authority_hash=auth,
    )
