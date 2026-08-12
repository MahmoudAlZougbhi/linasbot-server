"""LOC split: smart_messaging_api store/routes under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_smart_messaging_api_modules_under_500_lines() -> None:
    assert _line_count("modules/smart_messaging_api.py") < 500
    assert _line_count("modules/smart_messaging_api_store.py") < 500
    assert _line_count("modules/smart_messaging_api_templates.py") < 500
    assert _line_count("modules/smart_messaging_api_send_template.py") < 500
    assert _line_count("modules/smart_messaging_api_send_test.py") < 500
    assert _line_count("modules/smart_messaging_api_status.py") < 500
    assert _line_count("modules/smart_messaging_api_settings.py") < 500
    assert _line_count("modules/smart_messaging_api_preview.py") < 500


def test_smart_messaging_api_preserves_public_api() -> None:
    from modules.smart_messaging_api_store import _build_template_record, _migrate_templates
    from modules.smart_messaging_api_templates import _monty_whatsapp_language_code

    api = Path("modules/smart_messaging_api.py").read_text(encoding="utf-8")
    assert "from modules import smart_messaging_api_templates" in api
    assert "from modules import smart_messaging_api_preview" in api
    assert "from modules.smart_messaging_api_store import" in api
    assert callable(_build_template_record)
    assert callable(_migrate_templates)
    assert _monty_whatsapp_language_code("franco") == "ar"
    rec = _build_template_record("reminder_24h", {"ar": "x"})
    assert rec["ar"] == "x"
