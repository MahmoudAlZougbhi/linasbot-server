"""WAVE E: PG service_catalog HTTP is gone. Services live in CM prices.catalog."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mobile_services_pg_api_is_gone() -> None:
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "mobile_services_api" not in main
    assert not (ROOT / "modules" / "mobile_services_api.py").exists()
    assert not (ROOT / "services" / "service_catalog").exists()
