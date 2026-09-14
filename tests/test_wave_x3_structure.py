"""WAVE X3: channel and reply packages live under domain folders; old paths stay gone."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GONE = (
    "services/customer_reply_v2",
    "services/comments_inbox",
    "services/whatsapp_cloud",
    "services/whatsapp_adapters",
    "services/tiktok_business",
    "services/web_chat",
    "services/omnichannel",
)

KEEP = (
    "services/brain/reply/orchestrator.py",
    "services/live_chat/comments_inbox/threads.py",
    "services/integrations/whatsapp/smart_followup/worker.py",
    "services/integrations/whatsapp/adapters/whatsapp_factory.py",
    "services/integrations/tiktok",
    "services/integrations/web_chat",
    "services/integrations/omnichannel",
    "services/whatsapp_cloud_template_service.py",
    "dashboard/src/pages/public/Landing.jsx",
    "dashboard/src/pages/owner/OwnerOverview.jsx",
)


def test_wave_x3_old_packages_gone_new_packages_present() -> None:
    missing = [rel for rel in KEEP if not (ROOT / rel).exists()]
    leftover = [rel for rel in GONE if (ROOT / rel).exists()]
    assert not missing, missing
    assert not leftover, leftover


def test_wave_x3_live_imports_use_domain_packages() -> None:
    scheduler = (ROOT / "modules/event_handlers_scheduler.py").read_text(encoding="utf-8")
    comments_api = (ROOT / "modules/comments_inbox_api.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    keep = (ROOT / "docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    assert "services.integrations.whatsapp.smart_followup.worker" in scheduler
    assert "services.live_chat.comments_inbox" in comments_api
    assert "modules.web_chat_api" in main
    assert "modules.comments_inbox_api" in main
    assert "WAVE X3" in keep
    assert not (ROOT / "dashboard/src/pages/operator").exists()
