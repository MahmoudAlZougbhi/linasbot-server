"""Deterministic WhatsApp routing for appointment and human-agent requests on social DMs.

Normal Instagram/Facebook messages must reach the canonical Linas AI. This module only
intercepts after an explicit booking/human-agent (or tattoo-removal contact) intent, then
collects missing branch/gender one field at a time before returning a WhatsApp handoff.
"""

from __future__ import annotations

import time
import uuid

from services.social_contact_routing_detect import (  # noqa: F401
    DEFAULT_SOCIAL_WHATSAPP_CONTACTS,
    SOCIAL_BOOKING_PREFERENCE_MEMORY_PREFIX,
    SOCIAL_BOOKING_PREFERENCES_FIELD,
    SOCIAL_CHANNELS,
    SOCIAL_CONTACT_FLOW_TTL_SECONDS,
    SocialContactRouteResult,
    SocialContactScope,
    SocialContactScopeError,
    _ask_branch,
    _ask_gender,
    _explicit_handoff_intent,
    _explicit_preference_change,
    _is_cancel_handoff,
    _language,
    _laser_contact_reply,
    _message_gender_selection,
    _missing_contact,
    _tenant_id_from_user_data,
    _unsupported_service_refuse_reply,
    clear_social_contact_flow,
    detect_branch,
    is_appointment_request,
    is_social_channel,
    is_tattoo_removal_request,
    phone_digits,
    resolve_social_whatsapp_number,
    social_booking_preference_reply,
    wa_me_url,
)
from services.social_contact_routing_flow import (  # noqa: F401
    _clear_flow_state,
    _flow_scope,
    _get_flow_state,
    _is_topic_change_during_handoff,
    _is_valid_continuation,
    _set_flow_state,
    _state_expired,
    clear_social_booking_preference,
    get_social_booking_preference,
    restore_social_booking_preference,
    set_social_booking_preference,
    social_booking_preference_key,
)


def route_social_contact_request(
    message: str,
    user_data: dict,
    language: str | None = None,
    force_intent: str | None = None,
) -> SocialContactRouteResult | None:
    """Return a deterministic WhatsApp-handoff reply only for explicit social handoff flows.

    ``force_intent`` (from GPT/router) cannot start a new handoff by itself. A new flow
    starts only when the user message explicitly requests booking/human/tattoo contact.
    A branch must always come from the current explicit request or this same isolated
    active flow. A saved Men/Women booking preference may fill only the missing
    category after branch collection; it is scope-isolated and never copied into
    temporary handoff state.
    Pending branch/gender collection continues only on valid answers; greetings, cancels,
    topic changes, and expired state return None so the canonical AI handles the message.
    """
    explicit = _explicit_handoff_intent(message)
    try:
        state = _get_flow_state(user_data)
        saved_preference = get_social_booking_preference(user_data)
    except SocialContactScopeError:
        clear_social_contact_flow(user_data)
        if explicit:
            raise
        return None
    if state and _state_expired(state):
        _clear_flow_state(user_data)
        state = {}

    selected_gender, another_person_override = _message_gender_selection(message)
    explicit_preference_change = _explicit_preference_change(message)
    preference_to_persist: str | None = None

    # A direct preference change may happen outside a booking flow. It is the only
    # standalone social category message that produces a deterministic reply.
    if explicit_preference_change and selected_gender:
        if saved_preference != selected_gender:
            set_social_booking_preference(user_data, selected_gender)
            saved_preference = selected_gender
            preference_to_persist = selected_gender
        if not explicit and not state:
            return SocialContactRouteResult(
                reply="",
                intent="preference",
                gender=selected_gender,
                preference_to_persist=preference_to_persist,
            )

    if explicit:
        # A new user-authored booking/human request always replaces prior state.
        # Only fields present in this message may seed the new active flow.
        _clear_flow_state(user_data)
        state = {
            "flow_id": uuid.uuid4().hex,
            "status": "active",
            "intent": explicit,
            "started_at": time.time(),
        }
        if explicit == "human":
            # Owner inbox alert (Instagram/Facebook never enter waiting_human queue).
            try:
                from services.owner_alert_service import owner_alert_service

                scope_tenant = str(
                    user_data.get("tenant_id") or user_data.get("tenantId") or user_data.get("workspace_id") or ""
                ).strip()
                scope_channel = str(user_data.get("channel") or "").strip()
                try:
                    scope = _flow_scope(user_data)
                    scope_tenant = scope.tenant_id
                    scope_channel = scope.channel
                except SocialContactScopeError:
                    pass
                if not scope_tenant:
                    raise SocialContactScopeError("tenant_id required for social human alert")
                social_uid = str(user_data.get("user_id") or "").strip()
                if not social_uid:
                    phone = str(user_data.get("phone_number") or "")
                    if phone.startswith("room:"):
                        social_uid = phone[5:].strip()
                if not social_uid and user_data.get("social_sender_id"):
                    try:
                        from services.social_user_id import compose_social_user_id

                        social_uid = compose_social_user_id(
                            tenant_id=scope_tenant,
                            channel=scope_channel or "instagram",
                            asset_id=str(user_data.get("meta_account_id") or ""),
                            sender_id=str(user_data.get("social_sender_id") or ""),
                        )
                    except Exception:
                        social_uid = f"{scope_channel}:{user_data.get('social_sender_id')}"
                display_name = str(
                    user_data.get("user_name") or user_data.get("name") or user_data.get("profile_name") or ""
                )
                if not display_name and social_uid:
                    try:
                        import config as _cfg

                        display_name = str(_cfg.user_names.get(social_uid) or "")
                    except Exception:
                        display_name = ""
                owner_alert_service.emit_social_human_request(
                    tenant_id=scope_tenant,
                    customer_name=display_name,
                    user_id=social_uid or None,
                    conversation_id=str(user_data.get("current_conversation_id") or "") or None,
                    channel=scope_channel,
                    last_message=message,
                    trigger_source="social_explicit_human_request",
                )
            except Exception as alert_err:
                print(f"⚠️ social human owner alert failed: {alert_err}")

    active_intent = state.get("intent") if state.get("intent") in {"booking", "human"} else None

    # GPT/router hints may continue an already-open flow, but never open a new one alone.
    forced = force_intent if force_intent in {"booking", "human"} else None

    detected_intent = None
    if explicit:
        detected_intent = explicit
    elif active_intent and _is_valid_continuation(message, state):
        detected_intent = active_intent
    elif forced and active_intent == forced and _is_valid_continuation(message, state):
        detected_intent = forced
    elif forced and explicit:
        detected_intent = forced

    if active_intent and not detected_intent:
        if _is_topic_change_during_handoff(message, state):
            _clear_flow_state(user_data)
        return None

    if not detected_intent:
        if not state:
            _clear_flow_state(user_data)
        return None

    if _is_cancel_handoff(message) and not explicit:
        _clear_flow_state(user_data)
        return None

    state = (
        dict(state)
        if state
        else {
            "flow_id": uuid.uuid4().hex,
            "status": "active",
            "started_at": time.time(),
        }
    )
    state["intent"] = detected_intent

    detected_branch = detect_branch(message)
    if detected_branch:
        state["branch"] = detected_branch

    tattoo = bool(state.get("tattoo_removal")) or is_tattoo_removal_request(message)
    state["tattoo_removal"] = tattoo

    if selected_gender:
        state["gender"] = selected_gender
        if another_person_override:
            state["gender_source"] = "current_request_override"
        else:
            state["gender_source"] = "customer_selection"
            if saved_preference != selected_gender:
                set_social_booking_preference(user_data, selected_gender)
                saved_preference = selected_gender
                preference_to_persist = selected_gender
    state_gender = state.get("gender") if state.get("gender") in {"male", "female"} else None
    gender = state_gender or saved_preference

    lang = _language(language)
    _set_flow_state(user_data, state)

    if tattoo:
        # Confirmed clinic truth: tattoo removal is unsupported. Never return a WhatsApp number.
        reply = _unsupported_service_refuse_reply(lang)
        _clear_flow_state(user_data)
        return SocialContactRouteResult(
            reply,
            detected_intent,
            branch=None,
            gender=gender,
            contact_env=None,
            tattoo_removal=True,
            preference_to_persist=preference_to_persist,
        )

    branch = state.get("branch")
    if not branch:
        return SocialContactRouteResult(
            _ask_branch(lang),
            detected_intent,
            gender=gender,
            preference_to_persist=preference_to_persist,
        )
    if not gender:
        return SocialContactRouteResult(
            _ask_gender(lang),
            detected_intent,
            branch=branch,
            preference_to_persist=preference_to_persist,
        )

    env_name = f"SOCIAL_WHATSAPP_{branch.upper()}_{gender.upper()}"
    wa_phone = resolve_social_whatsapp_number(
        env_name,
        tenant_id=_tenant_id_from_user_data(user_data),
    )
    if not wa_phone:
        return SocialContactRouteResult(
            _missing_contact(lang),
            detected_intent,
            branch=branch,
            gender=gender,
            contact_env=env_name,
            preference_to_persist=preference_to_persist,
        )

    reply = _laser_contact_reply(lang, branch, wa_phone)
    _clear_flow_state(user_data)
    return SocialContactRouteResult(
        reply,
        detected_intent,
        branch=branch,
        gender=gender,
        contact_env=env_name,
        preference_to_persist=preference_to_persist,
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


def reset_social_contact_flow_for_sender(user_data: dict) -> bool:
    """Reset pending handoff for the current channel/account scope only."""
    before = _get_flow_state(user_data)
    _clear_flow_state(user_data)
    return bool(before)
