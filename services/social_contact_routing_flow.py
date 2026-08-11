"""Social contact routing flow state and booking preference helpers (LOC split)."""

from __future__ import annotations

import hashlib
import time

from services.conversation_router import get_gender_from_message

from services.social_contact_routing_detect import (
    SOCIAL_BOOKING_PREFERENCE_MEMORY_PREFIX,
    SOCIAL_BOOKING_PREFERENCES_FIELD,
    SOCIAL_CHANNELS,
    SOCIAL_CONTACT_FLOW_TTL_SECONDS,
    SocialContactScope,
    detect_branch,
    is_appointment_request,
    is_tattoo_removal_request,
    _explicit_handoff_intent,
    _is_cancel_handoff,
    _is_greeting_only,
    _other_person_booking_gender,
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


def _sender_fingerprint(sender_id: str) -> str:
    return hashlib.sha256(sender_id.encode("utf-8")).hexdigest()


def _flow_state_key(user_data: dict) -> str:
    """Key active handoff state by tenant, channel, business asset, and sender."""
    return f"social_contact_flow::v2::{_scope_fingerprint(_flow_scope(user_data))}"


def _purge_legacy_flow_state(user_data: dict) -> None:
    """Retire unsafe unscoped and pre-v2 flow blobs instead of migrating their fields."""
    user_data.pop("social_contact_flow", None)
    for key in list(user_data.keys()):
        if str(key).startswith("social_contact_flow::") and not str(key).startswith("social_contact_flow::v2::"):
            user_data.pop(key, None)


def _get_flow_state(user_data: dict) -> dict:
    _purge_legacy_flow_state(user_data)
    scope = _flow_scope(user_data)
    key = _flow_state_key(user_data)
    state = user_data.get(key)
    expected_fingerprint = key.rsplit("::", 1)[-1]
    if not isinstance(state, dict):
        return {}
    if (
        state.get("status") != "active"
        or state.get("intent") not in {"booking", "human"}
        or state.get("scope_fingerprint") != expected_fingerprint
        or state.get("tenant_id") != scope.tenant_id
        or state.get("channel") != scope.channel
        or state.get("business_asset_id") != scope.business_asset_id
        or state.get("sender_fingerprint") != _sender_fingerprint(scope.sender_id)
        or not isinstance(state.get("flow_id"), str)
        or not state.get("flow_id")
    ):
        user_data.pop(key, None)
        return {}
    return state


def _set_flow_state(user_data: dict, state: dict) -> None:
    scope = _flow_scope(user_data)
    key = _flow_state_key(user_data)
    state = dict(state)
    state["status"] = "active"
    state["scope_fingerprint"] = key.rsplit("::", 1)[-1]
    state["tenant_id"] = scope.tenant_id
    state["channel"] = scope.channel
    state["business_asset_id"] = scope.business_asset_id
    state["sender_fingerprint"] = _sender_fingerprint(scope.sender_id)
    state["updated_at"] = time.time()
    if "started_at" not in state:
        state["started_at"] = state["updated_at"]
    user_data[key] = state
    _purge_legacy_flow_state(user_data)


def _clear_flow_state(user_data: dict) -> None:
    _purge_legacy_flow_state(user_data)
    user_data.pop(_flow_state_key(user_data), None)


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


def _is_valid_continuation(message: str, state: dict) -> bool:
    """Only branch/gender answers (or re-stated handoff intent) continue a pending flow."""
    if detect_branch(message):
        return True
    if _other_person_booking_gender(message):
        return True
    if get_gender_from_message(message):
        return True
    if _explicit_handoff_intent(message):
        return True
    return False


def _is_topic_change_during_handoff(message: str, state: dict) -> bool:
    """Greetings, cancels, or non-answer text while waiting for branch/gender → return to AI."""
    if not state.get("intent"):
        return False
    if _is_cancel_handoff(message) or _is_greeting_only(message):
        return True
    # Waiting for a field but message is neither a valid answer nor a new handoff intent.
    return not _is_valid_continuation(message, state)
