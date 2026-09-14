"""BOC clinic booking is deleted from SaaS."""

from __future__ import annotations

from pathlib import Path

from services.product_features import (
    boc_appointment_jobs_allowed,
    boc_booking_enabled,
    boc_booking_readiness,
    boc_disabled_response,
)

ROOT = Path(__file__).resolve().parents[1]


def test_boc_is_not_in_saas() -> None:
    assert boc_booking_enabled() is False
    assert boc_appointment_jobs_allowed() is False
    payload = boc_disabled_response(operation="create_appointment")
    assert payload["success"] is False
    assert payload["error"] == "boc_not_in_saas"
    ready = boc_booking_readiness()
    assert ready["enabled"] is False
    assert ready["ok"] is True


def test_boc_env_cannot_reenable(monkeypatch) -> None:
    monkeypatch.setenv("LINASLASER_BOC_BOOKING_ENABLED", "true")
    assert boc_booking_enabled() is False


def test_booking_and_api_integrations_are_gone() -> None:
    assert not (ROOT / "services/booking").exists()
    assert not (ROOT / "services/api_integrations.py").exists()
    assert not (ROOT / "services/api_integrations_http.py").exists()
    assert (ROOT / "docs/BOC_NOT_IN_SAAS.md").is_file()
    assert "boc-lb.com" not in (ROOT / "api_config.py").read_text(encoding="utf-8")
