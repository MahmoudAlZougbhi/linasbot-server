"""Cross-node hot conversation session (Redis JSON blob + sidecar maps).

Process-local config.user_* dicts remain a per-request working copy.
Anything required for the next node to continue the same conversation
is loaded at turn start and saved at turn end.

TTL: 24h sliding. Writes are last-write-wins on the blob; combine text
chunks stay in the atomic combine list, not here.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_PREFIX = (os.getenv("LINAS_CONV_SESSION_PREFIX") or "linas:csess").strip() or "linas:csess"
_TTL_SEC = max(60, int(os.getenv("LINAS_CONV_SESSION_TTL_SEC") or "86400"))
_TEST_CLIENT: Any | None = None

_CONTINUITY_KEYS = (
    "current_conversation_id",
    "user_preferred_lang",
    "_text_turn_epoch",
    "_conversation_key",
    "awaiting_gender",
    "awaiting_clarification",
    "awaiting_name",
    "awaiting_name_input",
    "original_question",
    "clarification_target",
    "selected_service",
    "last_bot_question_type",
    "pending_clarification_query",
    "initial_user_query_to_process",
    "awaiting_human_handover_confirmation",
    "social_contact_flow",
    "social_booking_preferences",
    "last_user_message_at",
    "channel",
    "social_sender_id",
    "meta_account_id",
    "tenant_id",
    "meta_app_key",
    "meta_binding_id",
    "phone_number",
    "gender",
    "human_handover_active",
)

_SKIP_SUBSTR = ("token", "secret", "password", "credential", "access_key")
_SKIP_KEYS = {
    "_logical_reply_id",
    "_last_outbound_delivery",
    "_delivery_succeeded",
    "_credit_captured_for_turn",
    "_ai_credit_blocked",
    "_ai_turn_started",
    "_combine_adapter_close",
    "_inbound_event_id",
    "_linas_trace_id",
    "_ai_turn_trace_id",
    "_source_message_id",
    "_combine_mid",
    "_distributed_combine_scheduled",
    "_combine_generation",
    "_meta_social_lab_simulation",
}


class SessionStoreUnavailable(RuntimeError):
    """Redis session store is required but not reachable."""


def set_session_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def session_store_enabled() -> bool:
    if _TEST_CLIENT is not None:
        return True
    from services.scale.message_combine_policy import distributed_combine_enabled

    return distributed_combine_enabled()


def session_store_required() -> bool:
    return session_store_enabled() and _TEST_CLIENT is None


def _key(user_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_.:/" else "_" for c in user_id)[:200]
    return f"{_PREFIX}:{safe}"


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            rendered = _jsonable(item)
            if rendered is _DROP:
                continue
            out[str(key)] = rendered
        return out
    if isinstance(value, (list, tuple)):
        out_list = []
        for item in value:
            rendered = _jsonable(item)
            if rendered is _DROP:
                continue
            out_list.append(rendered)
        return out_list
    return _DROP


_DROP = object()


def _should_skip_key(key: str) -> bool:
    if key in _SKIP_KEYS:
        return True
    lowered = key.lower()
    return any(part in lowered for part in _SKIP_SUBSTR)


def _user_data_blob(user_data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in user_data.items():
        if _should_skip_key(str(key)):
            continue
        if str(key).startswith("_") and str(key) not in {"_text_turn_epoch", "_conversation_key"}:
            continue
        rendered = _jsonable(value)
        if rendered is _DROP:
            continue
        out[str(key)] = rendered
    for key in _CONTINUITY_KEYS:
        if key in user_data and key not in out:
            rendered = _jsonable(user_data[key])
            if rendered is not _DROP:
                out[key] = rendered
    return out


def load(user_id: str) -> dict[str, Any]:
    client = _client()
    if client is None:
        if session_store_required():
            raise SessionStoreUnavailable("conversation_session_redis_unavailable")
        return {}
    try:
        raw = client.get(_key(user_id))
    except Exception as exc:
        logger.warning("conv session load failed: %s", type(exc).__name__)
        if session_store_required():
            raise SessionStoreUnavailable("conversation_session_redis_unavailable") from exc
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save(user_id: str, blob: dict[str, Any]) -> bool:
    client = _client()
    if client is None:
        if session_store_required():
            raise SessionStoreUnavailable("conversation_session_redis_unavailable")
        return False
    payload = json.dumps(blob, separators=(",", ":"), ensure_ascii=False)
    try:
        client.set(_key(user_id), payload, ex=_TTL_SEC)
        return True
    except Exception as exc:
        logger.warning("conv session save failed: %s", type(exc).__name__)
        if session_store_required():
            raise SessionStoreUnavailable("conversation_session_redis_unavailable") from exc
        return False


def hydrate_into_process(user_id: str) -> dict[str, Any]:
    """Merge Redis session into process-local config maps. Returns user_data."""
    import config

    if user_id not in config.user_data_whatsapp or not config.user_data_whatsapp[user_id]:
        config.user_data_whatsapp[user_id] = {
            "user_preferred_lang": "ar",
            "initial_user_query_to_process": None,
            "awaiting_human_handover_confirmation": False,
            "current_conversation_id": None,
            **config.DEFAULT_CONVERSATION_STATE,
        }
    if not session_store_enabled():
        return config.user_data_whatsapp[user_id]
    blob = load(user_id)
    if not blob:
        return config.user_data_whatsapp[user_id]
    user_data = config.user_data_whatsapp[user_id]
    incoming = blob.get("user_data") if isinstance(blob.get("user_data"), dict) else {}
    user_data.update(incoming)
    name = str(blob.get("user_name") or "").strip()
    if name:
        config.user_names[user_id] = name
    gender = str(blob.get("gender") or "").strip()
    if gender:
        config.user_gender[user_id] = gender
    if "greeting_stage" in blob:
        try:
            config.user_greeting_stage[user_id] = int(blob.get("greeting_stage") or 0)
        except (TypeError, ValueError):
            pass
    if "takeover" in blob:
        config.user_in_human_takeover_mode[user_id] = bool(blob.get("takeover"))
    booking = blob.get("booking_state")
    if isinstance(booking, dict):
        config.user_booking_state[user_id] = dict(booking)
    if "photo_analysis_count" in blob:
        try:
            config.user_photo_analysis_count[user_id] = int(blob.get("photo_analysis_count") or 0)
        except (TypeError, ValueError):
            pass
    if "gender_attempts" in blob:
        try:
            config.gender_attempts[user_id] = int(blob.get("gender_attempts") or 0)
        except (TypeError, ValueError):
            pass
    return user_data


def persist_from_process(user_id: str) -> bool:
    """Snapshot process-local conversation maps into Redis."""
    if not session_store_enabled():
        return False
    import config

    user_data = dict(config.user_data_whatsapp.get(user_id) or {})
    last_bot = config.user_last_bot_response_time.get(user_id)
    blob = {
        "user_data": _user_data_blob(user_data),
        "user_name": str(config.user_names.get(user_id) or ""),
        "gender": str(config.user_gender.get(user_id) or ""),
        "greeting_stage": int(config.user_greeting_stage.get(user_id) or 0),
        "takeover": bool(config.user_in_human_takeover_mode.get(user_id)),
        "booking_state": _jsonable(dict(config.user_booking_state.get(user_id) or {})) or {},
        "photo_analysis_count": int(config.user_photo_analysis_count.get(user_id) or 0),
        "in_training": bool(config.user_in_training_mode.get(user_id)),
        "gender_attempts": int(config.gender_attempts.get(user_id) or 0),
        "last_bot_response_at": last_bot.isoformat() if isinstance(last_bot, datetime) else "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    if blob["booking_state"] is _DROP:
        blob["booking_state"] = {}
    ok = save(user_id, blob)
    try:
        from services.scale.conversation_state_redis import set_takeover

        set_takeover(user_id, bool(blob["takeover"]))
    except Exception:
        pass
    return ok
