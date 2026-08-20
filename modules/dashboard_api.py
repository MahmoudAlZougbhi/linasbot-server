"""
Dashboard API module: Testing and simulation endpoints
Provides endpoints for dashboard testing of the bot functionality.

Health: dashboard_api_health; lab leftovers: lab_message/lab_voice/lab_upload; helpers: dashboard_api_helpers (LOC split).
"""

from __future__ import annotations

# Register routes (import side effects).
from modules import channel_health_api as channel_health_api  # noqa: F401
from modules import dashboard_api_health as dashboard_api_health  # noqa: F401
from modules import dashboard_api_lab_message as dashboard_api_lab_message  # noqa: F401
from modules import dashboard_api_lab_upload as dashboard_api_lab_upload  # noqa: F401
from modules import dashboard_api_lab_voice as dashboard_api_lab_voice  # noqa: F401

# Re-export helpers for existing imports / monkeypatches.
from modules.dashboard_api_helpers import (  # noqa: F401
    _await_dashboard_delayed_task,
    _dashboard_empty_capture_hint,
    _refuse_disabled_lab_endpoint,
    _whatsapp_id_variants,
    dashboard_captured_list_for_user,
    dashboard_clear_captured_for_user,
    dashboard_send_message_capture,
    restore_user_state_from_firestore,
)
