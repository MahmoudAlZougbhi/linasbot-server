"""WAVE X5: no production lab=true; no Laser prod_migration seed; no Laser classifier catalog."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_wave_x5_workflows_do_not_write_lab_true() -> None:
    offenders: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT))
        if '"LINAS_CUSTOMER_AI_LAB": "true"' in text:
            offenders.append(f"{rel}:write_true")
        if '("LINAS_CUSTOMER_AI_LAB", "true")' in text:
            offenders.append(f"{rel}:assert_true")
        if "LINAS_CUSTOMER_AI_LAB=true" in text:
            offenders.append(f"{rel}:eq_true")
    assert not offenders, offenders

    apply_yml = (WORKFLOWS / "customer-brain-env-apply-ha.yml").read_text(encoding="utf-8")
    assert '"LINAS_CUSTOMER_AI_LAB": "false"' in apply_yml
    assert '("LINAS_CUSTOMER_AI_LAB", "false")' in apply_yml
    assert not (WORKFLOWS / "customer-brain-live-lab-ha.yml").exists()


def test_wave_x5_prod_migration_museum_is_gone() -> None:
    assert not (ROOT / "services/ai_setup/prod_migration.py").exists()
    assert not (ROOT / "services/ai_setup/section_classifier.py").exists()


def test_wave_x5_linaslaser_api_is_alias_of_external() -> None:
    config = (ROOT / "config.py").read_text(encoding="utf-8")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "EXTERNAL_API_BASE_URL" in config
    assert "LINASLASER_API_" not in config
    assert "BOC_BOOKING_ENABLED" in (ROOT / "services/product_features.py").read_text(encoding="utf-8")
    assert "LINASLASER_BOC_BOOKING_ENABLED" not in (ROOT / "services/product_features.py").read_text(encoding="utf-8")
    assert "Never set BOC_BOOKING_ENABLED" in example
    from services.product_features import boc_booking_enabled

    assert boc_booking_enabled() is False


def test_wave_x5_keep_surface_records_wave() -> None:
    keep = (ROOT / "docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    assert "WAVE X5" in keep
