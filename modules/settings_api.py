"""
Settings API Module
Handles application settings endpoints for the dashboard
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Request

from modules.api_security import require_session
from modules.core import app
from services.ai_limits_source import get_ai_limits_for_api
from services.ai_usage_limits import recommended_defaults
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
    """Read AI limits from published AI Setup (sole business SoT)."""
    session = require_session(request)
    payload = get_ai_limits_for_api(session.tenant_id)
    return {
        "success": True,
        "tenant_id": session.tenant_id,
        "recommended": recommended_defaults(),
        **payload,
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
                "name": "WhatsApp Cloud (outbound)",
                "service": "Meta Cloud API",
                "configured": _env_configured(
                    "WHATSAPP_API_TOKEN",
                    "WHATSAPP_PHONE_NUMBER_ID",
                    "WHATSAPP_TOKEN",
                    "META_WHATSAPP_TOKEN",
                ),
                "notes": "Not an inbound AI channel",
            },
            {
                "name": "Firebase",
                "service": "Conversations / Live Chat store",
                "configured": _firebase_credentials_configured(),
                "notes": "Aligned with FIRESTORE_SERVICE_ACCOUNT_KEY_PATH / data/firebase_data.json",
            },
        ]
        return {"success": True, "integrations": integrations}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _firebase_credentials_configured() -> bool:
    """Match Live Chat init paths so Settings readiness does not false-report Missing env."""
    candidates: list[str] = []
    for name in (
        "FIRESTORE_SERVICE_ACCOUNT_KEY_PATH",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "FIREBASE_CREDENTIALS_PATH",
    ):
        raw = (os.getenv(name) or "").strip()
        if raw:
            candidates.append(raw)
    candidates.extend(
        [
            "data/firebase_data.json",
            "firebase_data.json",
        ]
    )
    for path in candidates:
        if os.path.isfile(path):
            return True
    return False
