"""Integrations surgical cleanup: proven-dead islands stay gone; live adapters remain."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GONE = (
    "services/integrations/meta/meta_social_comment_sync.py",
    "services/integrations/meta/meta_social_publish.py",
    "services/integrations/meta/meta_social_post_confirm.py",
    "services/integrations/meta/meta_social_media_store.py",
    "services/integrations/meta/meta_comment_sync_cursors.py",
    "services/integrations/meta/meta_social_caption.py",
    "services/integrations/whatsapp/legacy_isolation.py",
    "services/integrations/tiktok/live_probe.py",
    "scripts/tiktok_enhanced_live_probe.py",
    "services/integrations/whatsapp/smart_followup",
    "services/integrations/whatsapp/smart_followup/eligibility.py",
    "services/integrations/whatsapp/smart_followup/constants.py",
    "services/integrations/whatsapp/smart_followup/business_hours.py",
)

KEEP = (
    "services/integrations/meta/meta_social_comment_sync_jobs.py",
    "services/integrations/tiktok/capability_probe.py",
    "services/integrations/tiktok/health.py",
    "services/smart_followup/worker.py",
    "services/integrations/web_chat/processor_v2_reply.py",
    "services/integrations/meta/meta_comment_replies.py",
    "services/integrations/meta/meta_comment_brain_send.py",
)


def test_integrations_dead_island_stays_gone() -> None:
    leftover = [rel for rel in GONE if (ROOT / rel).exists()]
    assert not leftover, leftover
    missing = [rel for rel in KEEP if not (ROOT / rel).exists()]
    assert not missing, missing
