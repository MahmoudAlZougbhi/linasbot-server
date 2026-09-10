"""Leftover smart-messaging HTTP is gone; workers use services only."""

from __future__ import annotations

from pathlib import Path


def test_smart_messaging_http_modules_removed() -> None:
    gone = (
        "modules/smart_messaging_api.py",
        "modules/smart_messaging_api_store.py",
        "modules/smart_messaging_api_templates.py",
        "modules/smart_messaging_api_send_template.py",
        "modules/smart_messaging_api_send_test.py",
        "modules/smart_messaging_api_status.py",
        "modules/smart_messaging_api_settings.py",
        "modules/smart_messaging_api_preview.py",
    )
    for rel in gone:
        assert not Path(rel).exists(), rel


def test_smart_messaging_services_remain_under_500_lines() -> None:
    keep = (
        "services/smart_messaging.py",
        "services/smart_messaging_deliver.py",
        "services/smart_messaging_templates.py",
        "services/whatsapp_cloud_template_service.py",
    )
    for rel in keep:
        assert Path(rel).is_file(), rel
        assert len(Path(rel).read_text(encoding="utf-8").splitlines()) < 500
