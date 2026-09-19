"""WAVE O1–O5: router/gender, translator, classifier, dashboard name, durable flag."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave_o1_no_unused_router_gender_bindings() -> None:
    ctx = (ROOT / "services/brain/inbound/text_handlers_respond_ctx.py").read_text(encoding="utf-8")
    router = (ROOT / "services/requests/human_detect.py").read_text(encoding="utf-8")
    assert "router_route" not in ctx
    assert "get_gender_from_message" not in ctx
    assert "def route(" not in router
    assert "ask_gender" not in router
    from services.requests.human_detect import is_human_request

    assert is_human_request("بدي احكي مع حدا") is True
    assert is_human_request("personal care tips") is False
    router = (ROOT / "services/requests/human_detect.py").read_text(encoding="utf-8")
    assert "GREETING_TEMPLATES" not in router


def test_wave_o2_no_laser_clinic_translator_in_brain() -> None:
    blob = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "services/brain").rglob("*.py"))
    assert "laser clinic" not in blob.lower()


def test_wave_o3_no_founder_branch_defaults_keep_antileak() -> None:
    assert not (ROOT / "services/ai_setup/section_classifier.py").exists()
    assert not (ROOT / "services/ai_setup/answer_packet.py").exists()


def test_wave_o4_dashboard_package_name() -> None:
    pkg = (ROOT / "dashboard/package.json").read_text(encoding="utf-8")
    lock = (ROOT / "dashboard/package-lock.json").read_text(encoding="utf-8")
    assert "linas-laser-dashboard" not in pkg
    assert "linas-laser-dashboard" not in lock
    assert '"name": "linas-ai-dashboard"' in pkg


def test_wave_o5_durable_bridge_key_and_ai_setup_paths() -> None:
    from services.ai_setup.durable_flags import (
        CM_DISABLE_LEGACY_BRIDGE,
        CM_DISABLE_LINAS_LEGACY_BRIDGE,
        parse_disable_legacy_bridge,
        readiness_requires_disable_bridge,
    )

    assert CM_DISABLE_LEGACY_BRIDGE == "CM_DISABLE_LEGACY_BRIDGE"
    assert parse_disable_legacy_bridge({CM_DISABLE_LINAS_LEGACY_BRIDGE: "true"}) is True
    flags = (ROOT / "services/ai_setup/durable_flags.py").read_text(encoding="utf-8")
    assert "CM_DISABLE_LEGACY_BRIDGE" in flags
    assert "linaslaserbot-2.7.22" not in flags
    for path in (ROOT / "services/ai_setup").rglob("*.py"):
        assert "linaslaserbot-2.7.22" not in path.read_text(encoding="utf-8"), path
    gate = readiness_requires_disable_bridge(
        linas_has_published_cm=True,
        effective_disable_bridge=True,
    )
    assert gate["ok"] is True


def test_wave_o1_o5_keep_portal_drawer_credits_catalog_ig() -> None:
    app = (ROOT / "dashboard/src/App.jsx").read_text(encoding="utf-8")
    drawer = (ROOT / "mobile/linas-ai/src/features/nav/drawerModules.ts").read_text(encoding="utf-8")
    assert 'path="/"' in app
    assert "OwnerLayout" in app or 'path="/owner"' in app or 'path="/owner/*"' in app
    assert drawer.count("id: '") + drawer.count('id: "') >= 9
    assert (ROOT / "services/billing/membership/message_catalog.py").is_file()
    assert (ROOT / "services/billing/credit_ledger_service.py").is_file()
    assert not (ROOT / "modules/local_qa_api.py").exists()
    from services.integrations.social.social_contact_routing_detect import is_social_channel

    assert is_social_channel("instagram") is True
    publish = (ROOT / "services/ai_setup/publish.py").read_text(encoding="utf-8")
    assert "from services.ai_setup.semantic_index import build_index" not in publish
    constants = (ROOT / "services/ai_setup/constants.py").read_text(encoding="utf-8")
    assert "brain_temporary_error" in constants
    assert (ROOT / "config.py").read_text(encoding="utf-8").count("user_booking_state") >= 1
    assert "user_in_training_mode" in (ROOT / "config.py").read_text(encoding="utf-8")
