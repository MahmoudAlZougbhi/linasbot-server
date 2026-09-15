"""LOC split: social_contact_routing detect/flow under 500 lines."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_social_contact_routing_modules_under_500_lines() -> None:
    assert _line_count("services/integrations/social/social_contact_routing.py") < 500
    assert _line_count("services/integrations/social/social_contact_routing_detect.py") < 500
    assert _line_count("services/integrations/social/social_contact_routing_flow.py") < 500


def test_social_contact_routing_preserves_keep_exports() -> None:
    from services.integrations.social import social_contact_routing as scr
    from services.integrations.social.social_contact_routing_detect import (
        DEFAULT_SOCIAL_WHATSAPP_CONTACTS,
        is_social_channel,
    )
    from services.integrations.social.social_contact_routing_flow import get_social_booking_preference

    assert scr.DEFAULT_SOCIAL_WHATSAPP_CONTACTS is DEFAULT_SOCIAL_WHATSAPP_CONTACTS
    assert scr.is_social_channel is is_social_channel
    assert scr.get_social_booking_preference is get_social_booking_preference
    assert callable(scr.expire_social_contact_flows_in_user_data)
    assert not hasattr(scr, "route_social_contact_request")
