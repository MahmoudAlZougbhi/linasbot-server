"""Public TikTok integration row for Integrations UI + dashboard."""

from __future__ import annotations

from typing import Any

from db.session import WhatsAppDatabaseUnavailable, whatsapp_db_configured, whatsapp_session
from services.tiktok_business.config import get_tiktok_settings
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.scopes import comments_manage_ready, comments_read_ready, messaging_send_ready


def _cap(*, level: str, supported: bool, permission: bool = False, notes: str = "") -> dict[str, Any]:
    return {
        "level": level,
        "supported_in_code": supported,
        "permission_present": permission,
        "app_review_advanced_access": False,
        "webhook_active": False,
        "live_verified": False,
        "notes": notes,
    }


def tiktok_integration_row(tenant_id: str) -> dict[str, Any]:
    settings = get_tiktok_settings()
    row: dict[str, Any] = {
        "platform": "tiktok",
        "label": "TikTok",
        "connected": False,
        "coming_soon": False,
        "connectable": bool(settings.configured),
        "binding_ids": [],
        "connection_status": "disconnected",
        "last_synced_at": None,
        "granted_scopes": [],
        "comments_state": _empty_state("disconnected", "connect_channel_first"),
        "dm_state": _empty_state("permission_pending", "tiktok_messaging_pending"),
        "account": None,
        "accounts": [],
        "capabilities": {
            "dm_read": _cap(
                level="needs_permission",
                supported=True,
                notes="Business Messaging requires TikTok product approval; not requested in OAuth.",
            ),
            "dm_reply": _cap(
                level="needs_permission",
                supported=True,
                notes="Capability-gated until message.list.read + send scopes are granted.",
            ),
            "comment_read": _cap(level="available", supported=True, notes="Get Account Comment"),
            "comment_reply": _cap(level="available", supported=True, notes="Manage Account Comment"),
            "webhooks": _cap(level="available", supported=True, notes="Messaging webhooks when approved"),
        },
        "production_redirect_uri": settings.redirect_uri,
    }
    if not settings.configured:
        row["connectable"] = False
        row["blocker_code"] = "TIKTOK_NOT_CONFIGURED"
        row["blocker_message"] = "TikTok Business credentials are not configured on the server."
        return row
    if not whatsapp_db_configured():
        row["connectable"] = False
        row["blocker_code"] = "TIKTOK_DB_UNAVAILABLE"
        return row
    try:
        with whatsapp_session() as session:
            repo = TikTokRepository(session)
            connection = repo.get_active_for_tenant(tenant_id)
            if connection is None:
                return row
            scopes = list(connection.granted_scopes or [])
            last_sync = connection.last_sync_at.timestamp() if connection.last_sync_at else None
            comments_ok = comments_manage_ready(scopes)
            comments_read = comments_read_ready(scopes)
            dm_ok = messaging_send_ready(scopes)
            from services.cm.actions import ACTION_TIKTOK_DM, comments_action_enabled, published_action_enabled

            comments_requested = comments_action_enabled(tenant_id, "tiktok")
            dm_requested = published_action_enabled(tenant_id, ACTION_TIKTOK_DM)
            row.update(
                {
                    "connected": connection.lifecycle_status == "connected" and comments_read,
                    "connectable": True,
                    "binding_ids": [connection.id],
                    "connection_status": connection.lifecycle_status,
                    "last_synced_at": last_sync,
                    "granted_scopes": scopes,
                    "account": {
                        "display_name": connection.display_name or connection.username or "TikTok",
                        "username": connection.username or None,
                        "profile_image_url": connection.avatar_url or None,
                        "connection_status": (
                            "connected" if connection.lifecycle_status == "connected" else "needs_reconnect"
                        ),
                        "last_synced_at": last_sync,
                    },
                    "comments_state": _state_from_connection(
                        requested=comments_requested,
                        permission=comments_ok or comments_read,
                        healthy=connection.lifecycle_status in {"connected", "permission_required"},
                        status=connection.comments_capability,
                        blocker=None if comments_read else "missing_comment_permissions",
                    ),
                    "dm_state": _state_from_connection(
                        requested=dm_requested,
                        permission=dm_ok,
                        healthy=connection.lifecycle_status == "connected",
                        status=connection.dm_capability,
                        blocker=None if dm_ok else "tiktok_messaging_pending",
                    ),
                }
            )
            row["accounts"] = [row["account"]]
            row["capabilities"]["comment_read"]["permission_present"] = comments_read
            row["capabilities"]["comment_read"]["level"] = "connected" if comments_read else "needs_permission"
            row["capabilities"]["comment_reply"]["permission_present"] = comments_ok
            row["capabilities"]["comment_reply"]["level"] = "connected" if comments_ok else "needs_permission"
            row["capabilities"]["dm_read"]["level"] = "connected" if dm_ok else "needs_permission"
            row["capabilities"]["dm_reply"]["level"] = "connected" if dm_ok else "needs_permission"
            row["never_active_without_scopes"] = not row["connected"] or comments_read
            # Honest: connected flag requires real comment read scopes, never messaging pretending.
            if row["connected"] and not comments_read and not dm_ok:
                row["connected"] = False
                row["connection_status"] = "permission_required"
    except WhatsAppDatabaseUnavailable:
        row["connectable"] = False
        row["blocker_code"] = "TIKTOK_DB_UNAVAILABLE"
    return row


def _empty_state(status: str, blocker: str) -> dict[str, Any]:
    return _state_from_connection(requested=False, permission=False, healthy=False, status=status, blocker=blocker)


def _state_from_connection(
    *, requested: bool, permission: bool, healthy: bool, status: str, blocker: str | None
) -> dict[str, Any]:
    return {
        "requested_enabled": requested,
        "permission_present": permission,
        "webhook_subscribed": status == "connected",
        "tenant_action_enabled": requested,
        "connection_healthy": healthy,
        "live_verified": False,
        "effective_enabled": bool(requested and permission and healthy),
        "missing_scopes": [],
        "blocker": blocker,
        "blocker_code": blocker,
        "blocker_message": _blocker_message(blocker),
        "status": status,
    }


def _blocker_message(code: str | None) -> str | None:
    if code == "connect_channel_first":
        return "Connect TikTok before enabling this capability."
    if code == "missing_comment_permissions":
        return "TikTok did not grant Get Account Comment / Manage Account Comment. Reconnect and approve those scopes."
    if code == "tiktok_messaging_pending":
        return "TikTok Business Messaging is pending TikTok approval. This is not a substitute using Data Portability."
    if code == "token_expired":
        return "TikTok token expired. Reconnect TikTok."
    return None
