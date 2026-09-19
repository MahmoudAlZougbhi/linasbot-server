"""Remaining-domain cleanup: dead CRV2/FAQ/SFU islands stay gone; SoT files stay."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_settings_crv2_search_island_is_gone() -> None:
    gone = (
        "services/products/crv2_tools.py",
        "services/products/resolution.py",
        "services/products/image_vision_rerank.py",
        "services/products/search.py",
        "services/products/search_scoring.py",
        "services/products/title_pages.py",
        "services/products/details_for_tera.py",
    )
    leftover = [rel for rel in gone if (ROOT / rel).exists()]
    assert leftover == []


def test_smart_followup_has_one_business_engine() -> None:
    assert not (ROOT / "services/smart_followup/social_schedule.py").exists()
    assert not (ROOT / "services/integrations/whatsapp/smart_followup").exists()
    facade = (ROOT / "modules/whatsapp_smart_followup_api.py").read_text(encoding="utf-8")
    assert "services.smart_followup" in facade
    assert "services.integrations.whatsapp.smart_followup" not in facade
    assert (ROOT / "services/smart_followup/worker.py").is_file()
    assert (ROOT / "services/smart_followup/generation.py").is_file()


def test_local_qa_and_faq_orphans_are_gone() -> None:
    gone = (
        "modules/local_qa_api.py",
        "modules/local_qa_api_helpers.py",
        "services/faq/local_qa_service.py",
        "services/faq/local_qa_service_match.py",
        "services/faq/faq_safe_match.py",
        "services/faq/faq_answer_localize.py",
        "services/faq/faq_cm_invalidation.py",
        "services/team/admin_provisioning_service.py",
    )
    leftover = [rel for rel in gone if (ROOT / rel).exists()]
    assert leftover == []
    assert (ROOT / "modules/cm_faq_api.py").is_file()
    assert (ROOT / "services/ai_setup/faq_invalidation.py").is_file()
    assert (ROOT / "services/team/provisioning_service.py").is_file()


def test_live_chat_has_no_local_qa_or_orphan_faq_helper() -> None:
    details = (ROOT / "services/live_chat/service_details.py").read_text(encoding="utf-8")
    assert "local_qa" not in details
    assert "read_qa_pairs" not in details
    assert "get_faq_match_context" not in details
    assert "def create_faq_pair_from_livechat" in (ROOT / "services/ai_setup/faq_integration.py").read_text(
        encoding="utf-8"
    )
