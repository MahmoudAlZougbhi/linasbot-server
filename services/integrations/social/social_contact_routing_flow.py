"""Social booking-preference restore and contact-flow TTL (Meta DM / persistence)."""

from __future__ import annotations

import hashlib
import time

from services.integrations.social.social_contact_routing_detect import (
    SOCIAL_BOOKING_PREFERENCE_MEMORY_PREFIX,
    SOCIAL_BOOKING_PREFERENCES_FIELD,
    SOCIAL_CHANNELS,
    SOCIAL_CONTACT_FLOW_TTL_SECONDS,
    SocialContactScope,
    SocialContactScopeError,
)


def _flow_scope(user_data: dict) -> SocialContactScope:
    tenant_id = str(user_data.get("tenant_id") or user_data.get("workspace_id") or "").strip()
    channel = str(user_data.get("channel") or "").strip().lower()
    business_asset_id = str(user_data.get("meta_account_id") or "").strip()
    sender_id = str(user_data.get("social_sender_id") or "").strip()
    if not tenant_id or channel not in SOCIAL_CHANNELS or not business_asset_id or not sender_id:
        raise SocialContactScopeError("Social handoff scope is incomplete")
    return SocialContactScope(
        tenant_id=tenant_id,
        channel=channel,
        business_asset_id=business_asset_id,
        sender_id=sender_id,
    )


def _scope_fingerprint(scope: SocialContactScope) -> str:
    components = (
        scope.tenant_id,
        scope.channel,
        scope.business_asset_id,
        scope.sender_id,
    )
    framed = "".join(f"{len(component)}:{component}" for component in components)
    return hashlib.sha256(framed.encode("utf-8")).hexdigest()


def social_booking_preference_key(user_data: dict) -> str:
    """Stable opaque key for one social customer's durable booking preference."""
    return _scope_fingerprint(_flow_scope(user_data))


def _preference_memory_key(user_data: dict) -> str:
    return f"{SOCIAL_BOOKING_PREFERENCE_MEMORY_PREFIX}{social_booking_preference_key(user_data)}"


def get_social_booking_preference(user_data: dict) -> str | None:
    """Return the validated in-memory preference for the current social scope."""
    value = user_data.get(_preference_memory_key(user_data))
    return value if value in {"male", "female"} else None


def set_social_booking_preference(user_data: dict, preference: str) -> None:
    """Cache a validated durable preference without touching temporary flow state."""
    if preference not in {"male", "female"}:
        raise ValueError("Invalid social booking preference")
    user_data[_preference_memory_key(user_data)] = preference


def clear_social_booking_preference(user_data: dict) -> None:
    """Discard an in-memory preference when the durable profile write failed."""
    user_data.pop(_preference_memory_key(user_data), None)


def restore_social_booking_preference(user_data: dict, persisted_state: dict) -> str | None:
    """Restore only this exact social scope from the existing customer profile document."""
    stored_preferences = persisted_state.get(SOCIAL_BOOKING_PREFERENCES_FIELD)
    if not isinstance(stored_preferences, dict):
        return None
    record = stored_preferences.get(social_booking_preference_key(user_data))
    if not isinstance(record, dict):
        return None
    preference = record.get("value")
    if not isinstance(preference, str) or preference not in {"male", "female"}:
        return None
    set_social_booking_preference(user_data, preference)
    return preference


def _state_expired(state: dict) -> bool:
    """Expire after SOCIAL_CONTACT_FLOW_TTL_SECONDS of inactivity (updated_at)."""
    if not state:
        return False
    stamp = state.get("updated_at")
    if stamp is None:
        stamp = state.get("started_at")
    try:
        stamp_f = float(stamp or 0)
    except (TypeError, ValueError):
        return True
    return (time.time() - stamp_f) > SOCIAL_CONTACT_FLOW_TTL_SECONDS
