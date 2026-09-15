"""WAVE P1: landing/lab/live-chat/mobile scrub; KEEP portal, drawer, credits, catalog."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave_p1_landing_clinic_copy_gone() -> None:
    landing = ROOT / "dashboard/src/components/landing"
    blob = "\n".join(path.read_text(encoding="utf-8") for path in landing.rglob("*.jsx"))
    assert "PigmentationSpotPreview" not in blob
    assert "product-serum" not in blob
    assert "Full body · 90 min" not in blob
    assert "30ml" not in blob
    assert not (landing / "cards/PigmentationSpotPreview.jsx").exists()
    assert (landing / "cards/PhotoQuestionPreview.jsx").is_file()


def test_wave_p1_faq_toolbar_and_legacy_scan_gone() -> None:
    assert not (ROOT / "mobile/linas-ai/src/features/faq/FaqListToolbar.tsx").exists()
    assert not (ROOT / "services/live_chat/service_legacy_scan.py").exists()
    service = (ROOT / "services/live_chat/service.py").read_text(encoding="utf-8")
    assert "LiveChatLegacyScanMixin" not in service
    assert "_legacy_active_scan_for_fallback" not in service


def test_wave_p1_lab_not_on_production_import_path() -> None:
    assert not (ROOT / "services/brain/test_lab.py").exists()
    assert not (ROOT / "services/brain/lab_feedback.py").exists()
    assert (ROOT / "tests/cm_test_lab.py").is_file()
    modules = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "modules").glob("*.py"))
    assert "cm_test_lab" not in modules
    assert "brain.test_lab" not in modules
    assert "lab_feedback" not in modules
    apply_yml = (ROOT / ".github/workflows/customer-brain-env-apply-ha.yml").read_text(encoding="utf-8")
    assert '"LINAS_CUSTOMER_AI_LAB": "false"' in apply_yml
    assert '"LINAS_CUSTOMER_AI_LAB": "true"' not in apply_yml


def test_wave_p1_boc_env_renamed_fail_closed() -> None:
    from services.product_features import BOC_BOOKING_ENABLED_ENV, boc_booking_enabled

    assert BOC_BOOKING_ENABLED_ENV == "BOC_BOOKING_ENABLED"
    assert boc_booking_enabled() is False
    features = (ROOT / "services/product_features.py").read_text(encoding="utf-8")
    assert "LINASLASER_BOC_BOOKING_ENABLED" not in features


def test_wave_p1_keep_portal_drawer_credits_catalog() -> None:
    app = (ROOT / "dashboard/src/App.jsx").read_text(encoding="utf-8")
    drawer = (ROOT / "mobile/linas-ai/src/features/nav/drawerModules.ts").read_text(encoding="utf-8")
    assert 'path="/"' in app
    assert "OwnerLayout" in app or 'path="/owner"' in app or 'path="/owner/*"' in app
    assert drawer.count("id: '") + drawer.count('id: "') >= 9
    assert (ROOT / "services/billing/membership/message_catalog.py").is_file()
    assert (ROOT / "services/billing/credit_ledger_service.py").is_file()
    from services.integrations.social.social_contact_routing_detect import is_social_channel

    assert is_social_channel("instagram") is True
    assert (ROOT / "modules/local_qa_api.py").is_file()
    webhook = (ROOT / "modules/wallet_api.py").read_text(encoding="utf-8")
    assert "token_pack_retired" in webhook
