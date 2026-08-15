"""Public widget config payload builder."""

from __future__ import annotations

from typing import Any

from services.web_chat.appearance import contrast_warnings
from services.web_chat.config_models import WebChatWidgetConfig
from services.web_chat.processor import evaluate_web_ai_eligibility


def build_public_widget_config(
    widget: WebChatWidgetConfig,
    *,
    eligible: bool | None = None,
    blocker: str | None = None,
) -> dict[str, Any]:
    if eligible is None or blocker is None:
        eligible, blocker = evaluate_web_ai_eligibility(widget.tenant_id, widget)
    appearance = widget.appearance
    return {
        "widget_key": widget.widget_key,
        "enabled": widget.enabled,
        "integration_mode": widget.integration_mode,
        "appearance": appearance,
        "contrast_warnings": contrast_warnings(appearance),
        "ai_available": eligible,
        "blocker_code": blocker,
    }
