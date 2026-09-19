"""Wave 2: founder WhatsApp matrix gone; human detect stays on requests.human_detect."""

from __future__ import annotations

import os

os.environ.setdefault("EXTERNAL_API_BASE_URL", "https://example.com")
os.environ.setdefault("EXTERNAL_API_TOKEN", "test-token")
os.environ.setdefault("DASHBOARD_AUTH_SECRET", "wave2-test-secret")

from services.requests.human_detect import is_human_request
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
    assert is_human_request("personal care tips") is False


def test_arabic_human_detected():
    assert is_human_request("بدي احكي مع حدا") is True
