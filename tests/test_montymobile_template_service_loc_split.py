"""LOC split: montymobile_template_service payload mixin under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services.montymobile_template_service import MontyMobileTemplateService, montymobile_template_service
from services.montymobile_template_service_payload import MontyMobileTemplatePayloadMixin


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_montymobile_template_service_modules_under_500_lines() -> None:
    assert _line_count("services/montymobile_template_service.py") < 500
    assert _line_count("services/montymobile_template_service_payload.py") < 500


def test_montymobile_template_service_preserves_public_api() -> None:
    assert isinstance(montymobile_template_service, MontyMobileTemplateService)
    assert isinstance(montymobile_template_service, MontyMobileTemplatePayloadMixin)
    assert callable(montymobile_template_service.get_template_info)
    assert callable(montymobile_template_service.build_template_payload)
    assert callable(montymobile_template_service.send_template_message)
    assert callable(montymobile_template_service.templates_are_text_only)
    assert callable(montymobile_template_service.resolve_whatsapp_language_for_template)
