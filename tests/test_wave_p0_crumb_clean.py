"""WAVE P0: dead museum deletes; KEEP social channel, catalog, credits, portal."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave_p0_dead_modules_gone() -> None:
    gone = (
        "services/billing/token_package_catalog.py",
        "services/ai_setup/shadow_eval.py",
        "services/ai_setup/cutover.py",
        "services/ai_setup/sot_audit.py",
        "services/products/crv2_tools_stub.py",
        "services/brain/inbound/VERSION.py",
        "utils/appointment_slot_rules.py",
        "utils/reminder_analytics.py",
    )
    leftover = [rel for rel in gone if (ROOT / rel).exists()]
    assert not leftover, leftover
    assert not (ROOT / "services/ai_setup/semantic_index.py").exists()


def test_wave_p0_no_laser_hair_intent_or_dead_booking_helpers() -> None:
    inbound = ROOT / "services/brain/inbound"
    blob = "\n".join(path.read_text(encoding="utf-8") for path in inbound.glob("*.py"))
    assert "LASER_HAIR_INTENT_KEYWORDS" not in blob
    assert "_flow_meta_has_crm_booking_confirmation" not in blob
    assert "_booking_not_confirmed_safe_reply" not in blob
    assert "_reply_claims_booking_done" not in blob
    assert "_classify_booking_offer_confirmation_reply" not in blob
    assert "_build_booking_followup_question" not in blob
    assert "_build_booking_decline_reply" not in blob
    assert "_is_laser_hair_intent" not in blob
    assert "route_social_contact_request" not in blob


def test_wave_p0_ai_setup_has_no_nested_runtime_path() -> None:
    for path in (ROOT / "services/ai_setup").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "linaslaserbot-2.7.22" not in text, path


def test_wave_p0_health_brand_is_saas() -> None:
    health = (ROOT / "modules/dashboard_api_health.py").read_text(encoding="utf-8")
    init = (ROOT / "modules/__init__.py").read_text(encoding="utf-8")
    assert "Lina's Laser AI Bot" not in health
    assert "Lina’s Laser AI Bot" not in health
    assert "Linas Laser" not in health
    assert "Lina's Laser AI Bot" not in init
    assert "Linas AI is running." in health


def test_wave_p0_systemd_brand_and_live_cert_generic() -> None:
    unit = (ROOT / "deploy/systemd/linasbot.service").read_text(encoding="utf-8")
    worker = (ROOT / "deploy/systemd/linasbot-worker@.service").read_text(encoding="utf-8")
    assert "Description=Linas AI\n" in unit
    assert "Linas Laser" not in unit
    assert "Linas Laser" not in worker
    assert "MAX_GENDER_ASK_ATTEMPTS" not in (ROOT / "config.py").read_text(encoding="utf-8")
    live = ROOT / "_live_cert"
    blob = "\n".join(path.read_text(encoding="utf-8") for path in live.rglob("*.py") if path.is_file())
    for token in ("Antelias", "Beirut", "أنطلياس", "بيروت", "Beyrouth"):
        assert token not in blob, token


def test_wave_p0_keep_social_channel_and_expire() -> None:
    from services.integrations.social.social_contact_routing import (
        DEFAULT_SOCIAL_WHATSAPP_CONTACTS,
        expire_social_contact_flows_in_user_data,
    )
    from services.integrations.social.social_contact_routing_detect import is_social_channel

    assert is_social_channel("instagram") is True
    assert DEFAULT_SOCIAL_WHATSAPP_CONTACTS == {}
    assert callable(expire_social_contact_flows_in_user_data)
    sfu = (ROOT / "services/smart_followup/social_schedule.py").read_text(encoding="utf-8")
    assert "is_social_channel" in sfu


def test_wave_p0_keep_portal_drawer_credits_catalog() -> None:
    app = (ROOT / "dashboard/src/App.jsx").read_text(encoding="utf-8")
    drawer = (ROOT / "mobile/linas-ai/src/features/nav/drawerModules.ts").read_text(encoding="utf-8")
    assert 'path="/"' in app
    assert "OwnerLayout" in app or 'path="/owner"' in app or 'path="/owner/*"' in app
    assert drawer.count("id: '") + drawer.count('id: "') >= 9
    assert (ROOT / "services/billing/membership/message_catalog.py").is_file()
    assert (ROOT / "services/billing/credit_ledger_service.py").is_file()
    assert (ROOT / "services/ai_setup/publish.py").is_file()
    from services.integrations.social.social_contact_routing_detect import is_social_channel

    assert callable(is_social_channel)
    publish = (ROOT / "services/ai_setup/publish.py").read_text(encoding="utf-8")
    assert "from services.ai_setup.semantic_index import build_index" not in publish
