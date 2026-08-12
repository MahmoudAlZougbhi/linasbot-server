"""LOC split: message_preview_service settings/queue under 500 lines; Monty adapters preserved."""

from __future__ import annotations

from pathlib import Path

from services.message_preview_service import MessagePreviewService, message_preview_service
from services.message_preview_service_queue import MessagePreviewQueueMixin
from services.message_preview_service_settings import MessagePreviewSettingsMixin


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_message_preview_service_modules_under_500_lines() -> None:
    assert _line_count("services/message_preview_service.py") < 500
    assert _line_count("services/message_preview_service_settings.py") < 500
    assert _line_count("services/message_preview_service_queue.py") < 500


def test_message_preview_service_preserves_public_api_and_monty_adapters() -> None:
    assert issubclass(MessagePreviewService, MessagePreviewSettingsMixin)
    assert issubclass(MessagePreviewService, MessagePreviewQueueMixin)
    assert isinstance(message_preview_service, MessagePreviewService)
    for name in (
        "get_template_header_image_url",
        "diagnose_template_header_image_sources",
        "_montymobile_templates_config_path",
        "_default_header_url_from_montymobile_templates_file",
        "add_to_preview_queue",
        "approve_message",
        "validate_message",
        "render_message_preview",
    ):
        assert callable(getattr(message_preview_service, name))
