"""KEEP: expire/restore + published contact resolve. Laser wa.me router deleted."""

from __future__ import annotations

from services.integrations.social.social_contact_routing_detect import (  # noqa: F401
    DEFAULT_SOCIAL_WHATSAPP_CONTACTS,
    SOCIAL_BOOKING_PREFERENCE_MEMORY_PREFIX,
    SOCIAL_BOOKING_PREFERENCES_FIELD,
    SOCIAL_CHANNELS,
    SOCIAL_CONTACT_FLOW_TTL_SECONDS,
    SocialContactScope,
    SocialContactScopeError,
    clear_social_contact_flow,
    is_social_channel,
    resolve_social_whatsapp_number,
)
from services.integrations.social.social_contact_routing_flow import (  # noqa: F401
    _state_expired,
    clear_social_booking_preference,
    get_social_booking_preference,
    restore_social_booking_preference,
    set_social_booking_preference,
    social_booking_preference_key,
)


def expire_social_contact_flows_in_user_data(user_data: dict) -> int:
    """Clear expired/invalid social handoff blobs on a user_data dict. Returns cleared count."""
    cleared = 0
    for key in list(user_data.keys()):
        if key != "social_contact_flow" and not str(key).startswith("social_contact_flow::"):
            continue
        state = user_data.get(key)
        key_text = str(key)
        key_fingerprint = key_text.rsplit("::", 1)[-1]
        if (
            not key_text.startswith("social_contact_flow::v2::")
            or not isinstance(state, dict)
            or state.get("status") != "active"
            or state.get("intent") not in {"booking", "human"}
            or state.get("scope_fingerprint") != key_fingerprint
            or not isinstance(state.get("flow_id"), str)
            or not state.get("flow_id")
            or _state_expired(state)
        ):
            user_data.pop(key, None)
            cleared += 1
    return cleared
