"""LOC split: WhatsApp Cloud template service payload mixin under 500 lines."""

from __future__ import annotations

from pathlib import Path

from services.whatsapp_cloud_template_service import (
    WhatsAppCloudTemplateService,
    whatsapp_cloud_template_service,
)
from services.whatsapp_cloud_template_service_payload import WhatsAppCloudTemplatePayloadMixin


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_whatsapp_cloud_template_service_modules_under_500_lines() -> None:
    assert _line_count("services/whatsapp_cloud_template_service.py") < 500
    assert _line_count("services/whatsapp_cloud_template_service_payload.py") < 500


def test_whatsapp_cloud_template_service_preserves_public_api() -> None:
    assert isinstance(whatsapp_cloud_template_service, WhatsAppCloudTemplateService)
    assert isinstance(whatsapp_cloud_template_service, WhatsAppCloudTemplatePayloadMixin)
    assert callable(whatsapp_cloud_template_service.get_template_info)
    assert callable(whatsapp_cloud_template_service.build_template_payload)
    assert callable(whatsapp_cloud_template_service.send_template_message)
    assert callable(whatsapp_cloud_template_service.templates_are_text_only)
    assert callable(whatsapp_cloud_template_service.resolve_whatsapp_language_for_template)
