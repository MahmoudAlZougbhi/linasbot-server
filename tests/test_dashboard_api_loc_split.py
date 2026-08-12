"""LOC split: dashboard_api health vs lab leftovers under 500 lines."""

from __future__ import annotations

from pathlib import Path

from modules.dashboard_api_helpers import (
    _refuse_disabled_lab_endpoint,
    dashboard_captured_list_for_user,
    dashboard_clear_captured_for_user,
    dashboard_send_message_capture,
    restore_user_state_from_firestore,
)


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_dashboard_api_modules_under_500_lines() -> None:
    assert _line_count("modules/dashboard_api.py") < 500
    assert _line_count("modules/dashboard_api_helpers.py") < 500
    assert _line_count("modules/dashboard_api_health.py") < 500
    assert _line_count("modules/dashboard_api_lab_message.py") < 500
    assert _line_count("modules/dashboard_api_lab_voice.py") < 500
    assert _line_count("modules/dashboard_api_lab_upload.py") < 500


def test_dashboard_api_preserves_helper_exports_and_route_modules() -> None:
    from modules import (
        dashboard_api,
        dashboard_api_health,
        dashboard_api_lab_message,
        dashboard_api_lab_upload,
        dashboard_api_lab_voice,
    )

    assert dashboard_api._refuse_disabled_lab_endpoint is _refuse_disabled_lab_endpoint
    assert callable(dashboard_api.restore_user_state_from_firestore)
    assert dashboard_api.dashboard_send_message_capture is dashboard_send_message_capture
    assert callable(dashboard_clear_captured_for_user)
    assert callable(dashboard_captured_list_for_user)
    assert callable(restore_user_state_from_firestore)
    assert callable(dashboard_api_health.health)
    assert callable(dashboard_api_health.ready)
    assert "whatsapp_cloud_credentials" in Path("modules/dashboard_api_health.py").read_text(encoding="utf-8")
    assert "montymobile_api_key" not in Path("modules/dashboard_api_health.py").read_text(encoding="utf-8")
    assert callable(dashboard_api_lab_message.test_message)
    assert callable(dashboard_api_lab_voice.test_voice)
    assert callable(dashboard_api_lab_upload.test_voice_upload)
