"""Wave 2: founder WhatsApp matrix gone; human intent stays on Brain planner."""

from __future__ import annotations

import os

os.environ.setdefault("EXTERNAL_API_BASE_URL", "https://example.com")
os.environ.setdefault("EXTERNAL_API_TOKEN", "test-token")
os.environ.setdefault("DASHBOARD_AUTH_SECRET", "wave2-test-secret")

from services.brain.planner.heuristic import plan_message
from services.integrations.social.social_contact_routing import (
    DEFAULT_SOCIAL_WHATSAPP_CONTACTS,
    is_social_channel,
)


def test_contact_matrix_empty():
    assert DEFAULT_SOCIAL_WHATSAPP_CONTACTS == {}


def test_is_social_channel():
    assert is_social_channel("instagram") is True
    assert is_social_channel("facebook") is True
    assert is_social_channel("whatsapp") is False


def test_personal_care_not_human():
    types = {task.type for task in plan_message("personal care tips").tasks}
    assert "human_request" not in types
    assert types == {"information"}


def test_heuristic_does_not_keyword_detect_human():
    types = {task.type for task in plan_message("بدي احكي مع حدا").tasks}
    assert types == {"information"}
