"""WAVE X4: KEEP backends stay enabled; museum stays disabled; marketing+portal routes exist."""

from __future__ import annotations

from pathlib import Path

from modules.api_security import is_keep_tenant_api_path
from services.product_features import DISABLED_API_PREFIXES, is_disabled_api_path

ROOT = Path(__file__).resolve().parents[1]

KEEP_API_SAMPLES = (
    "/api/cm/publish",
    "/api/live-chat/unified-chats",
    "/api/comments/media",
    "/api/comments/inbox",
    "/api/requests",
    "/api/whatsapp/smart-followup/settings",
    "/api/owner-copilot/chat",
    "/api/web-chat/config",
    "/api/meta/connections",
    "/api/billing/status",
    "/api/faq/save-all-languages",
)

MUSEUM_API_SAMPLES = (
    "/api/smart-messaging",
    "/api/test-message",
    "/api/settings/clinic",
    "/api/meta/social-posts",
)


def test_wave_x4_keep_apis_are_not_product_disabled() -> None:
    for path in KEEP_API_SAMPLES:
        assert is_disabled_api_path(path) is False, path
        assert is_keep_tenant_api_path(path) is True, path
    for path in MUSEUM_API_SAMPLES:
        assert is_disabled_api_path(path) is True, path
        assert is_keep_tenant_api_path(path) is False, path
    assert "/api/live-chat" not in DISABLED_API_PREFIXES
    assert "/api/cm" not in DISABLED_API_PREFIXES
    assert "/api/owner-copilot" not in DISABLED_API_PREFIXES


def test_wave_x4_marketing_portal_and_domain_packages() -> None:
    app = (ROOT / "dashboard/src/App.jsx").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    keep = (ROOT / "docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    assert 'path="/" element={<Landing />}' in app
    assert "OwnerOverview" in app
    assert "path=\"/features\"" in app or "path='/features'" in app
    assert "/owner/lab" not in app
    for needle in (
        "modules.cm_api",
        "modules.live_chat_api",
        "modules.whatsapp_smart_followup_api",
        "modules.owner_copilot_api",
        "modules.web_chat_api",
        "modules.comments_inbox_api",
    ):
        assert needle in main
    for rel in (
        "services/brain/reply",
        "services/live_chat/comments_inbox",
        "services/integrations/whatsapp",
        "services/integrations/tiktok",
        "services/integrations/web_chat",
        "services/smart_followup",
        "services/owner_copilot",
    ):
        assert (ROOT / rel).is_dir(), rel
    assert "WAVE X4" in keep
