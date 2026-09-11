"""User-facing Enhanced Video Context status for Integrations."""

from __future__ import annotations

from typing import Any

from services.tiktok_business.ads_config import tiktok_ads_redirect_uri
from services.tiktok_business.capabilities import (
    ENHANCED_LABEL,
    empty_capabilities,
    user_message_for,
)
from services.tiktok_business.repository_enhanced import TikTokEnhancedRepository
from services.tiktok_business.scopes import comments_manage_ready, comments_read_ready


def _account_caps(granted: Any) -> dict[str, bool]:
    caps = empty_capabilities()
    caps["account_basic"] = True
    caps["video_list"] = True
    caps["comments_read"] = comments_read_ready(granted)
    caps["comments_manage"] = comments_manage_ready(granted)
    return caps


def enhanced_status_block(
    *,
    tenant_id: str,
    connection: Any | None,
    session: Any | None = None,
) -> dict[str, Any]:
    caps = _account_caps(getattr(connection, "granted_scopes", None) if connection is not None else None)
    status = "authorization_required"
    reason = "authorization_required"
    last_probe_at = None
    identity_id = ""
    if connection is None:
        status = "authorization_required"
        reason = "authorization_required"
    elif session is not None:
        enhanced = TikTokEnhancedRepository(session)
        binding = enhanced.get_binding(tenant_id=tenant_id, connection_id=connection.id)
        if binding is None:
            status = "authorization_required"
            reason = "authorization_required"
        else:
            status = binding.status or "authorization_required"
            reason = binding.reason_code or status
            caps.update({k: bool(v) for k, v in dict(binding.capabilities or {}).items()})
            last_probe_at = binding.last_probe_at.timestamp() if binding.last_probe_at else None
            identity_id = binding.identity_id or ""
    post_level = "enhanced" if status in {"active", "limited"} and identity_id else "basic"
    can_authorize = connection is not None and status in {
        "authorization_required",
        "identity_authorization_required",
        "reauthorization_required",
        "waiting_for_permission",
        "error",
        "limited",
    }
    return {
        "post_context": {"level": post_level},
        "enhanced_video_context": {
            "label": ENHANCED_LABEL,
            "status": status,
            "reason_code": reason,
            "user_message": user_message_for(status),
            "can_authorize": bool(can_authorize),
            "capabilities": caps,
            "last_probe_at": last_probe_at,
            "production_ads_redirect_uri": tiktok_ads_redirect_uri(),
        },
    }
