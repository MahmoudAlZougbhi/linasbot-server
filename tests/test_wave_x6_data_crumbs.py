"""WAVE X6: preview/gender gone; no founder phones in git; eval names off prod Laser."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave_x6_preview_and_gender_gone() -> None:
    gone = (
        "services/message_preview_service.py",
        "services/message_preview_service_queue.py",
        "services/message_preview_service_settings.py",
        "services/gender_recognition_service.py",
        "data/message_preview_queue.json",
        "services/brain/evals/linas_real_index.py",
        "services/brain/evals/golden_pack_linas.py",
    )
    leftover = [rel for rel in gone if (ROOT / rel).exists()]
    assert not leftover, leftover
    keep = (
        "services/integrations/whatsapp/template_header_image.py",
        "services/integrations/whatsapp/cloud_template_payload.py",
        "services/billing/membership/message_catalog.py",
    )
    missing = [rel for rel in keep if not (ROOT / rel).exists()]
    assert not missing, missing
    payload = (ROOT / "services/integrations/whatsapp/cloud_template_payload.py").read_text(encoding="utf-8")
    assert "services.integrations.whatsapp.template_header_image" in payload
    assert "message_preview_service" not in payload


def test_wave_x6_phone_map_has_no_clinic_pii() -> None:
    mapping = ROOT / "data/phone_to_room_mapping.json"
    assert not mapping.exists()
    blob = ""
    for path in (ROOT / "data").glob("*.json"):
        blob += path.read_text(encoding="utf-8")
    assert "76466674" not in blob
    assert "+961" not in blob


def test_wave_x6_app_settings_has_no_museum_keys() -> None:
    settings = json.loads((ROOT / "data/app_settings.json").read_text(encoding="utf-8"))
    assert "smartMessaging" not in settings
    assert "booking" not in settings
    assert "pricingSync" not in settings
    general = settings.get("general") or {}
    assert "enableTraining" not in general
    blob = (ROOT / "data/app_settings.json").read_text(encoding="utf-8")
    assert "templateSchedules" not in blob
    assert "areaToBodyPartIds" not in blob


def test_wave_x6_evals_not_prod_laser_defaults() -> None:
    keep = (ROOT / "docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    readiness = (ROOT / "services/brain/readiness.py").read_text(encoding="utf-8")
    qa = (ROOT / "services/brain/evals/qa_tenants.py").read_text(encoding="utf-8")
    runner = (ROOT / "services/brain/evals/live_lab_runner.py").read_text(encoding="utf-8")
    assert "WAVE X6" in keep
    assert "live_lab_latest.json" not in readiness
    assert "def shop_a_qa_sections" in qa
    assert "linas_like_qa_sections" not in qa
    assert "Linas Laser" not in qa
    assert 'LAB_TENANT = "eval-lab-a"' in runner
    from services.brain.evals.golden_pack import run_golden_pack
    from services.integrations.whatsapp.template_header_image import get_template_header_image_url

    assert callable(run_golden_pack)
    assert callable(get_template_header_image_url)
