"""Redacted WhatsApp Cloud App Review readiness payload. Never includes secrets."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select

from db.models.whatsapp_cloud import WhatsAppConnectionAttempt
from db.session import whatsapp_session
from services.whatsapp_cloud.config import (
    WHATSAPP_COEXISTENCE_FEATURE,
    get_whatsapp_cloud_flags,
    whatsapp_config_key_presence,
)
from services.whatsapp_cloud.repository import WhatsAppCloudRepository, connection_public_view


def whatsapp_rollout_fingerprint() -> str:
    flags = get_whatsapp_cloud_flags()
    payload = {
        "coexistence_feature": WHATSAPP_COEXISTENCE_FEATURE,
        "public_availability": flags.public_availability,
        "connection_ui_enabled": flags.connection_ui_enabled,
        "webhook_side_effects_enabled": flags.webhook_side_effects_enabled,
        "outbound_sends_enabled": flags.outbound_sends_enabled,
        "ai_replies_enabled": flags.ai_replies_enabled,
        "history_sync_enabled": flags.history_sync_enabled,
        "require_pilot_entitlement": flags.require_pilot_entitlement,
        "embedded_signup_config_configured": flags.embedded_signup_config_id_configured,
        "graph_api_version": flags.graph_api_version,
        "keys": whatsapp_config_key_presence(),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _redirect_host() -> str:
    flags = get_whatsapp_cloud_flags()
    return urlparse(flags.oauth_redirect_uri).netloc or ""


def build_app_review_readiness(*, tenant_id: str = "linas") -> dict[str, Any]:
    flags = get_whatsapp_cloud_flags()
    tid = str(tenant_id or "").strip().lower() or "linas"
    with whatsapp_session() as session:
        repo = WhatsAppCloudRepository(session)
        pilot = repo.get_active_pilot(tid)
        connections = [
            connection_public_view(conn, ai_eligible=bool(conn.ai_default_enabled))
            | {
                "connection_source": conn.connection_source,
                "history_sync_status": conn.history_sync_status,
                "display_phone_last4": conn.display_phone_last4,
                "verified_name": conn.verified_name,
            }
            for conn in repo.list_tenant_connections(tid, include_revoked=False)
            if conn.lifecycle_status != "revoked"
        ]
        attempts = list(
            session.scalars(
                select(WhatsAppConnectionAttempt)
                .where(WhatsAppConnectionAttempt.tenant_id == tid)
                .order_by(WhatsAppConnectionAttempt.created_at.desc())
                .limit(10)
            ).all()
        )
        attempt_rows = [
            {
                "status": row.status,
                "outcome_code": row.outcome_code,
                "return_surface": row.return_surface,
                "feature_type": row.feature_type,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in attempts
        ]
    return {
        "success": True,
        "tenant_id": tid,
        "public_availability": flags.public_availability,
        "coexistence_feature": WHATSAPP_COEXISTENCE_FEATURE,
        "graph_api_version": flags.graph_api_version,
        "oauth_redirect_host": _redirect_host(),
        "rollout_fingerprint": whatsapp_rollout_fingerprint(),
        "flags": {
            "connection_ui_enabled": flags.connection_ui_enabled,
            "webhook_side_effects_enabled": flags.webhook_side_effects_enabled,
            "outbound_sends_enabled": flags.outbound_sends_enabled,
            "ai_replies_enabled": flags.ai_replies_enabled,
            "history_sync_enabled": flags.history_sync_enabled,
            "public_availability": flags.public_availability,
            "require_pilot_entitlement": flags.require_pilot_entitlement,
            "embedded_signup_config_configured": flags.embedded_signup_config_id_configured,
        },
        "config_keys_present": whatsapp_config_key_presence(),
        "bind_token_present": bool((os.getenv("META_WHATSAPP_APP_REVIEW_BIND_TOKEN") or "").strip()),
        "pilot": {
            "active": pilot is not None,
            "status": getattr(pilot, "status", None),
        },
        "connections": connections,
        "connection_count": len(connections),
        "attempts": attempt_rows,
        "never_includes": ["access_token", "app_secret", "bind_token", "full_phone_number"],
    }
