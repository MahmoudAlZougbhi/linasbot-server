"""Diagnostic channel health. Never a load-balancer or HA deploy gate."""

from __future__ import annotations

from typing import Any

from services.meta_app_registry import (
    MetaAppRegistry,
    diagnose_active_meta_binding,
    get_meta_app_registry,
    meta_multi_app_registry_enabled,
)
from services.meta_messaging import get_meta_messaging_settings

_META_CHANNELS = ("facebook", "instagram")


def _result(*, status: str, connected: bool, reason: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status, "connected": connected}
    if reason:
        payload["reason"] = reason
    return payload


def evaluate_channel_health(*, registry: MetaAppRegistry | None = None) -> dict[str, Any]:
    """Per-channel PASS / WARNING / FAIL. HTTP 200 always; not an LB signal."""

    payload: dict[str, Any] = {
        "role": "channel_health",
        "lb_gate": False,
    }
    payload.update(_meta_channels(registry=registry))
    payload["whatsapp"] = _whatsapp_channel()
    payload["tiktok"] = _tiktok_channel()
    payload["web_chat"] = _web_chat_channel()
    return payload


def _meta_channels(*, registry: MetaAppRegistry | None) -> dict[str, dict[str, Any]]:
    by_channel: dict[str, list[Any]] = {name: [] for name in _META_CHANNELS}
    if meta_multi_app_registry_enabled():
        try:
            current = registry or get_meta_app_registry()
            for binding in current.list_bindings(include_inactive=False):
                channel = str(getattr(binding, "channel", "") or "")
                if channel in by_channel:
                    by_channel[channel].append(binding)
            return {name: _summarize_meta_channel(name, by_channel[name], current) for name in _META_CHANNELS}
        except Exception:
            failed = _result(status="FAIL", connected=False, reason="registry_unavailable")
            return {name: dict(failed) for name in _META_CHANNELS}

    settings = get_meta_messaging_settings()
    facebook_connected = bool(settings.page_id and settings.page_access_token)
    instagram_connected = bool(settings.instagram_account_id)
    return {
        "facebook": _result(
            status="PASS" if facebook_connected else "WARNING",
            connected=facebook_connected,
            reason=None if facebook_connected else "no_active_binding",
        ),
        "instagram": _result(
            status="PASS" if instagram_connected else "WARNING",
            connected=instagram_connected,
            reason=None if instagram_connected else "no_active_binding",
        ),
    }


def _summarize_meta_channel(channel: str, bindings: list[Any], registry: MetaAppRegistry) -> dict[str, Any]:
    if not bindings:
        return _result(status="WARNING", connected=False, reason="no_active_binding")
    failures: list[str] = []
    for binding in bindings:
        reason = diagnose_active_meta_binding(registry, binding)
        if reason:
            failures.append(reason)
    if failures:
        return _result(status="FAIL", connected=True, reason=failures[0])
    return _result(status="PASS", connected=True)


def _whatsapp_channel() -> dict[str, Any]:
    try:
        from sqlalchemy import select

        from db.models.whatsapp_cloud import WhatsAppConnection
        from db.session import whatsapp_db_configured, whatsapp_session
        from services.whatsapp_cloud.repository_helpers import ACTIVE_LIFECYCLES

        if not whatsapp_db_configured():
            return _result(status="WARNING", connected=False, reason="no_active_binding")
        with whatsapp_session() as session:
            rows = list(session.scalars(select(WhatsAppConnection)).all())
        active = [row for row in rows if row.lifecycle_status in ACTIVE_LIFECYCLES]
        if not active:
            return _result(status="WARNING", connected=False, reason="no_active_binding")
        broken = [row for row in active if row.lifecycle_status in {"needs_attention", "failed"}]
        if broken:
            return _result(status="FAIL", connected=True, reason=str(broken[0].lifecycle_status))
        connected = any(row.lifecycle_status == "connected" for row in active)
        if connected:
            return _result(status="PASS", connected=True)
        return _result(status="WARNING", connected=False, reason="no_active_binding")
    except Exception:
        return _result(status="WARNING", connected=False, reason="no_active_binding")


def _tiktok_channel() -> dict[str, Any]:
    try:
        from sqlalchemy import select

        from db.models.tiktok_business import TikTokConnection
        from db.session import whatsapp_db_configured, whatsapp_session

        if not whatsapp_db_configured():
            return _result(status="WARNING", connected=False, reason="no_active_binding")
        with whatsapp_session() as session:
            rows = list(session.scalars(select(TikTokConnection)).all())
        active = [row for row in rows if row.lifecycle_status not in {"disconnected", "revoked"}]
        if not active:
            return _result(status="WARNING", connected=False, reason="no_active_binding")
        broken = [row for row in active if row.lifecycle_status in {"token_expired", "error"}]
        if broken:
            return _result(status="FAIL", connected=True, reason=str(broken[0].lifecycle_status))
        connected = any(row.lifecycle_status == "connected" for row in active)
        if connected:
            return _result(status="PASS", connected=True)
        return _result(status="WARNING", connected=False, reason="no_active_binding")
    except Exception:
        return _result(status="WARNING", connected=False, reason="no_active_binding")


def _web_chat_channel() -> dict[str, Any]:
    try:
        from sqlalchemy import select

        from db.session import whatsapp_db_configured, whatsapp_session
        from services.web_chat.config_models import config_from_raw
        from services.web_chat.pg_models import WebChatWidgetRow

        if not whatsapp_db_configured():
            return _result(status="WARNING", connected=False, reason="no_active_binding")
        with whatsapp_session() as session:
            rows = list(session.scalars(select(WebChatWidgetRow)).all())
        widgets = [config_from_raw(row.tenant_id, dict(row.config or {})) for row in rows]
        connected_widgets = [widget for widget in widgets if widget.connected]
        if connected_widgets:
            return _result(status="PASS", connected=True)
        return _result(status="WARNING", connected=False, reason="no_active_binding")
    except Exception:
        return _result(status="WARNING", connected=False, reason="no_active_binding")
