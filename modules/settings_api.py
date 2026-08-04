"""
Settings API Module
Handles application settings endpoints for the dashboard
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Request

from modules.api_security import require_permission, require_session
from modules.core import app
from services.ai_usage_limits import ai_usage_limits_service, recommended_defaults
from services.settings_service import settings_service


def _env_configured(*names: str) -> bool:
    return any(bool((os.getenv(n) or "").strip()) for n in names)


@app.get("/api/settings")
async def get_settings() -> Any:
    """Get all application settings"""
    try:
        settings = settings_service.get_all_settings()
        return {"success": True, "settings": settings}
    except Exception as e:
        print(f"❌ Error getting settings: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/settings/ai-limits")
async def get_ai_limits(request: Request) -> Any:
    """Per-tenant AI capability limits (images + context lines per end-user)."""
    session = require_session(request)
    limits = ai_usage_limits_service.get_settings(session.tenant_id)
    return {
        "success": True,
        "tenant_id": session.tenant_id,
        "limits": limits.to_public_dict(),
        "recommended": recommended_defaults(),
    }


@app.post("/api/settings/ai-limits")
async def update_ai_limits(updates: dict[str, Any], request: Request) -> Any:
    """Save per-tenant AI capability limits (settings permission required)."""
    session = require_permission(request, "settings")
    body = updates if isinstance(updates, dict) else {}
    # Nested {limits: {...}} or flat body both accepted.
    payload = body.get("limits") if isinstance(body.get("limits"), dict) else body
    limits = ai_usage_limits_service.save_settings(session.tenant_id, payload)
    return {
        "success": True,
        "tenant_id": session.tenant_id,
        "limits": limits.to_public_dict(),
        "message": "AI limits saved",
    }

@app.get("/api/settings/integrations")
async def get_integration_status() -> Any:
    """
    Redacted integration readiness for the dashboard.
    Never returns secret values — only configured / missing flags.
    """
    try:
        meta_registry_configured = False
        try:
            from services.meta_app_registry import (
                get_meta_registry_readiness,
                meta_multi_app_registry_enabled,
            )

            if meta_multi_app_registry_enabled():
                meta_registry_configured = get_meta_registry_readiness()[0]
        except Exception:
            meta_registry_configured = False
        integrations: list[dict[str, Any]] = [
            {
                "name": "OpenAI",
                "service": "Chat / Whisper",
                "configured": _env_configured("OPENAI_API_KEY"),
                "notes": "Required for AI replies",
            },
            {
                "name": "Meta Instagram / Facebook",
                "service": "Social messaging webhooks",
                "configured": meta_registry_configured
                or _env_configured(
                    "META_APP_SECRET",
                    "META_PAGE_ACCESS_TOKEN",
                    "FACEBOOK_PAGE_ACCESS_TOKEN",
                    "INSTAGRAM_PAGE_ACCESS_TOKEN",
                ),
                "notes": "First-party App A plus staged Tech Provider App B; inbound DMs only",
            },
            {
                "name": "WhatsApp provider (outbound handoff / CRM)",
                "service": "MontyMobile / Dialog / Cloud",
                "configured": _env_configured(
                    "MONTYMOBILE_API_KEY",
                    "DIALOG360_API_KEY",
                    "WHATSAPP_TOKEN",
                    "META_WHATSAPP_TOKEN",
                ),
                "notes": "Not an inbound AI channel",
            },
            {
                "name": "Firebase",
                "service": "Conversations / Live Chat store",
                "configured": _env_configured(
                    "GOOGLE_APPLICATION_CREDENTIALS",
                    "FIREBASE_CREDENTIALS_PATH",
                )
                or os.path.exists("firebase_data.json"),
                "notes": "Path presence only; credentials never returned",
            },
        ]
        return {"success": True, "integrations": integrations}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/settings/{category}")
async def update_settings(category: str, updates: dict[str, Any]) -> Any:
    """
    Update settings in a specific category

    Args:
        category: Settings category (general, notifications, security)
        updates: Dictionary of settings to update
    """
    try:
        # Validate category
        valid_categories = ["general", "notifications", "security", "clinic"]
        if category not in valid_categories:
            return {"success": False, "error": f"Invalid category. Must be one of: {valid_categories}"}

        # Keep notification recipients normalized even when updated via generic endpoint.
        if category == "notifications" and "humanTakeoverNotifyMobiles" in updates:
            updates["humanTakeoverNotifyMobiles"] = settings_service.normalize_human_takeover_notify_mobiles(
                updates.get("humanTakeoverNotifyMobiles", "")
            )

        # Update settings
        success = settings_service.update_settings(category, updates)

        if success:
            return {
                "success": True,
                "message": "Settings updated successfully",
                "category": category,
                "updated": updates,
            }
        else:
            return {"success": False, "error": "Failed to save settings"}
    except Exception as e:
        print(f"❌ Error updating settings: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.get("/api/settings/notifications/human-takeover-mobiles")
async def get_human_takeover_mobiles() -> Any:
    """Get mobile numbers for human takeover notifications"""
    try:
        mobile_numbers = settings_service.get_human_takeover_notify_mobiles()
        mobile_numbers_list = settings_service.get_human_takeover_notify_mobiles_list()
        return {"success": True, "mobile_numbers": mobile_numbers, "mobile_numbers_list": mobile_numbers_list}
    except Exception as e:
        print(f"❌ Error getting human takeover mobiles: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/settings/notifications/human-takeover-mobiles")
async def set_human_takeover_mobiles(data: dict[str, Any]) -> Any:
    """Set mobile numbers for human takeover notifications"""
    try:
        mobile_numbers = data.get("mobile_numbers", "")
        if isinstance(mobile_numbers, list):
            mobile_numbers = ", ".join(str(item) for item in mobile_numbers if str(item).strip())
        elif mobile_numbers is None:
            mobile_numbers = ""
        else:
            mobile_numbers = str(mobile_numbers)

        success = settings_service.set_human_takeover_notify_mobiles(mobile_numbers)
        normalized_numbers = settings_service.get_human_takeover_notify_mobiles()

        if success:
            return {
                "success": True,
                "message": "Mobile numbers updated successfully",
                "mobile_numbers": normalized_numbers,
                "mobile_numbers_list": settings_service.get_human_takeover_notify_mobiles_list(),
            }
        else:
            return {"success": False, "error": "Failed to save mobile numbers"}
    except Exception as e:
        print(f"❌ Error setting human takeover mobiles: {e}")
        return {"success": False, "error": str(e)}
