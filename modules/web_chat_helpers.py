"""Shared Web Chat API helpers."""

from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException, Request

from modules.api_security import _client_ip
from services.rate_limit_service import rate_limit_service
from services.web_chat.appearance import contrast_warnings
from services.web_chat.config_models import WebChatWidgetConfig
from services.web_chat.embed import build_embed_snippet, public_api_base
from services.web_chat.flags import web_chat_containment_active
from services.web_chat.processor import evaluate_web_ai_eligibility
from services.web_chat.store import web_chat_store


def reject_if_web_chat_contained() -> None:
    if web_chat_containment_active():
        raise HTTPException(
            status_code=503,
            detail={"error": "WEB_CHAT_UNAVAILABLE", "message": "Website chat is not available."},
        )


def rate_limit_widget(request: Request, *, session_id: str, widget_key: str) -> None:
    ip = _client_ip(request)
    for key, limit, window in (
        (f"web-chat:ip:{ip}", 60, 300),
        (f"web-chat:sid:{session_id}", 30, 300),
        (f"web-chat:key:{widget_key}", 120, 300),
    ):
        allowed, retry = rate_limit_service.hit(key, limit=limit, window_seconds=window)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={"error": "RATE_LIMIT", "retry_after": retry},
                headers={"Retry-After": str(retry)},
            )


def web_membership_gate(tenant_id: str) -> tuple[bool, str | None]:
    from services.membership.web_gate import WebPlanDenied, assert_web_plan_allowed

    try:
        assert_web_plan_allowed(tenant_id)
    except WebPlanDenied as exc:
        return False, str(exc)
    return True, None


def installation_status(widget: WebChatWidgetConfig) -> str:
    if not widget.enabled:
        return "disabled"
    if not widget.site_url.strip():
        return "waiting"
    last_seen = widget.installation.last_seen_at
    if last_seen is None:
        return "waiting"
    if time.time() - float(last_seen) > 86400:
        return "waiting"
    last_origin = widget.installation.last_origin.strip()
    if last_origin and not web_chat_store.origin_allowed_for_widget(widget, last_origin):
        return "domain_mismatch"
    return "connected"


def widget_payload(widget: WebChatWidgetConfig, *, tenant_id: str | None = None) -> dict[str, Any]:
    tid = tenant_id or widget.tenant_id
    eligible, blocker = evaluate_web_ai_eligibility(tid, widget)
    status = installation_status(widget)
    return {
        "widget_key": widget.widget_key,
        "integration_public_id": widget.integration_public_id,
        "site_url": widget.site_url,
        "enabled": widget.enabled,
        "connected": widget.connected,
        "operational": eligible,
        "installation_status": status,
        "blocker_code": blocker,
        "integration_mode": widget.integration_mode,
        "appearance": widget.appearance,
        "contrast_warnings": contrast_warnings(widget.appearance),
        "installation": {
            "last_seen_at": widget.installation.last_seen_at,
            "last_origin": widget.installation.last_origin,
            "installed": widget.installation.installed,
        },
        "embed_snippet": build_embed_snippet(widget_key=widget.widget_key),
        "widget_script_url": f"{public_api_base()}/web-chat/widget.js",
        "sdk_docs_url": f"{public_api_base()}/web-chat/sdk-docs",
    }


def mobile_web_chat_payload(tenant_id: str, widget: WebChatWidgetConfig) -> dict[str, Any]:
    membership_allows, membership_message = web_membership_gate(tenant_id)
    payload = widget_payload(widget, tenant_id=tenant_id)
    payload["membership_allows"] = membership_allows
    payload["membership_message"] = membership_message
    return payload


def resolve_widget_or_404(widget_key: str) -> WebChatWidgetConfig:
    widget = web_chat_store.get_widget_by_key(widget_key)
    if widget is None:
        raise HTTPException(status_code=404, detail={"error": "WIDGET_NOT_FOUND"})
    return widget


def assert_origin_allowed(widget: WebChatWidgetConfig, origin: str | None) -> None:
    if not web_chat_store.origin_allowed_for_widget(widget, origin):
        raise HTTPException(status_code=403, detail={"error": "ORIGIN_NOT_ALLOWED"})
