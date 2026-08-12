"""LOC split: social_contact_routing detect/flow under 500 lines."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_social_contact_routing_modules_under_500_lines() -> None:
    assert _line_count("services/social_contact_routing.py") < 500
    assert _line_count("services/social_contact_routing_detect.py") < 500
    assert _line_count("services/social_contact_routing_flow.py") < 500


def test_social_contact_routing_preserves_public_exports() -> None:
    from services import social_contact_routing as scr
    from services.social_contact_routing_detect import (
        DEFAULT_SOCIAL_WHATSAPP_CONTACTS,
        is_appointment_request,
    )
    from services.social_contact_routing_flow import get_social_booking_preference

    assert scr.DEFAULT_SOCIAL_WHATSAPP_CONTACTS is DEFAULT_SOCIAL_WHATSAPP_CONTACTS
    assert scr.is_appointment_request is is_appointment_request
    assert scr.get_social_booking_preference is get_social_booking_preference
    assert callable(scr.route_social_contact_request)
