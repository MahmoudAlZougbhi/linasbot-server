"""WAVE X12: inbound handlers under Brain; remaining flat services folded."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave_x12_handlers_package_gone() -> None:
    assert not (ROOT / "handlers").exists()
    assert (ROOT / "services/brain/inbound/text_handlers.py").is_file()
    assert (ROOT / "modules/webhook_handlers_photo.py").is_file()
    assert (ROOT / "modules/webhook_handlers.py").is_file()
    webhook = (ROOT / "modules/webhook_handlers.py").read_text(encoding="utf-8")
    assert "from services.brain.inbound.text_handlers import handle_message" in webhook
    assert "from handlers" not in webhook


def test_wave_x12_flat_services_are_tiny_keep_facades() -> None:
    flats = sorted(p.name for p in (ROOT / "services").glob("*.py"))
    assert flats == [
        "__init__.py",
        "product_features.py",
        "saas_no_boc.py",
        "safe_path.py",
        "ssrf_guard.py",
    ]
    assert not (ROOT / "services/credit_ai_gate.py").exists()
    assert not (ROOT / "services/ai_reply_lifecycle.py").exists()
    assert (ROOT / "services/billing/credit_ai_gate.py").is_file()
    assert (ROOT / "services/brain/ai_reply/ai_reply_lifecycle.py").is_file()
    assert (ROOT / "services/guest/guest_ai_service.py").is_file()
    assert (ROOT / "services/billing/membership/message_catalog.py").is_file()


def test_wave_x12_keep_drawer_portal_and_inventory() -> None:
    app = (ROOT / "dashboard/src/App.jsx").read_text(encoding="utf-8")
    portal = app + (ROOT / "dashboard/src/owner_portal/OwnerPortalRoutes.jsx").read_text(encoding="utf-8")
    drawer = (ROOT / "mobile/linas-ai/src/features/nav/drawerModules.ts").read_text(encoding="utf-8")
    assert 'path="/"' in app
    assert "OwnerLayout" in portal or 'path="/owner"' in portal
    assert drawer.count("id: '") + drawer.count('id: "') >= 9
    assert (ROOT / "services/scale/delivery_ledger.py").is_file()
    assert (ROOT / "deploy/README.md").is_file()
    from services.billing.credit_ai_gate import ai_generation_blocked
    from services.brain.inbound.text_handlers import handle_message
    from services.owner_copilot.welcome_pool import pick_welcome

    assert callable(handle_message)
    assert callable(ai_generation_blocked)
    assert callable(pick_welcome)
