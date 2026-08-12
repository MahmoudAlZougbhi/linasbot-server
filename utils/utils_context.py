"""In-memory and Firestore conversation context for GPT."""

from __future__ import annotations

import asyncio
import datetime
import logging
from collections import deque
from typing import Any, cast

import config
from services.live_chat_contracts import (
    parse_timestamp_utc,
    utc_now,
)
from utils.utils_firestore import get_firestore_db
from utils.utils_livechat_hooks import _latest_smart_ai_across_conversations

_log = logging.getLogger(__name__)


def append_turn_to_user_context_memory(user_id: str, role: str, text: str) -> None:
    """
    In-process ring buffer of recent turns (OpenAI shape) for GPT context.
    Used when Firestore history is shorter (e.g. TESTING_MODE skips saves, or replication lag).
    """
    if not user_id or not text or not str(text).strip():
        return
    uid = str(user_id).strip()
    if uid not in config.user_context:
        config.user_context[uid] = deque(maxlen=config.MAX_CONTEXT_MESSAGES)
    r = (role or "").strip().lower()
    if r == "user":
        oai_role = "user"
    elif r in ("ai", "assistant", "operator"):
        oai_role = "assistant"
    else:
        oai_role = "assistant"
    config.user_context[uid].append(
        {
            "role": oai_role,
            "content": str(text).strip(),
            "timestamp": utc_now(),
        }
    )


def _filter_in_memory_context_for_window(mem: list, window_hours: int) -> list:
    """
    Apply the same time window discipline to in-process memory as Firestore context.
    Entries without timestamps are excluded when a positive window is enforced, so stale
    RAM-only history cannot bypass the configured context window.
    """
    if not mem:
        return []
    if not window_hours or int(window_hours) <= 0:
        return list(mem)
    cutoff = utc_now() - datetime.timedelta(hours=int(window_hours))
    filtered = []
    for msg in mem:
        ts_raw = msg.get("timestamp")
        if ts_raw is None:
            continue
        msg_ts = parse_timestamp_utc(ts_raw, fallback=None)
        if msg_ts is not None and msg_ts >= cutoff:
            filtered.append(msg)
    return filtered


async def get_conversation_context_for_gpt(
    user_id: str,
    conversation_id: str,
    *,
    window_hours: int | None = None,
    alternate_user_id: str | None = None,
) -> list:
    """
    Loads Firestore history for the configured time window, then prefers the in-memory transcript
    when it contains strictly more turns (testing / save-skipped paths).
    """
    wh = window_hours if window_hours is not None else int(getattr(config, "CONTEXT_WINDOW_HOURS", 12) or 12)
    fs = await get_conversation_history_from_firestore(
        user_id,
        conversation_id,
        max_messages=0,
        window_hours=wh,
        alternate_user_id=alternate_user_id,
    )
    mem = _filter_in_memory_context_for_window(
        list(config.user_context.get(str(user_id).strip()) or []),
        wh,
    )
    if len(mem) > len(fs):
        cap = int(getattr(config, "MAX_CONTEXT_MESSAGES_IN_WINDOW", 0) or 0)
        use = mem[-cap:] if cap > 0 else mem
        openai_safe = [
            {
                "role": msg.get("role", "user"),
                "content": str(msg.get("content", "") or ""),
            }
            for msg in use
        ]
        print(f"ℹ️ GPT context: in-memory transcript ({len(use)} msgs) > Firestore ({len(fs)}); using in-memory.")
        return openai_safe
    return fs


async def get_conversation_history_from_firestore(
    user_id: str,
    conversation_id: str,
    max_messages: int = 0,
    window_hours: int | None = None,
    alternate_user_id: str | None = None,
) -> list:
    """
    Fetches conversation history from Firestore for a specific conversation.
    Returns a list of messages in OpenAI format: [{"role": "user"/"assistant", "content": "text"}]
    Tries user_id first, then alternate_user_id (e.g. canonical), since save uses canonical_user_id.

    Args:
        user_id: The user's ID (room_id for Qiscus / raw WhatsApp id)
        conversation_id: The conversation document ID
        max_messages:  max number of messages after time filtering (0 = no hard cap)
        window_hours:  lookback window in hours (None = use config.CONTEXT_WINDOW_HOURS)
        alternate_user_id:  alternate user id (e.g. canonical) to try if user_id doc not found

    Returns:
        List of message dicts in OpenAI format
    """
    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Returning empty conversation history.")
        return []

    app_id_for_firestore = "linas-ai-bot-backend"
    users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
    candidate_ids = [user_id]
    if alternate_user_id and alternate_user_id != user_id:
        candidate_ids.append(alternate_user_id)

    doc_snap = None
    used_uid = None
    for uid in candidate_ids:
        if not uid:
            continue
        conv_doc_ref = (
            users_coll.document(uid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
        )
        try:
            doc_snap = conv_doc_ref.get()
            if doc_snap.exists:
                used_uid = uid
                break
        except Exception as e:
            print(f"⚠️ get_conversation_history try uid={uid}: {e}")
            continue

    if not doc_snap or not doc_snap.exists:
        print(f"⚠️ Conversation {conversation_id} not found for user(s) {candidate_ids}")
        return []

    try:
        conversation_data = doc_snap.to_dict()
        messages = conversation_data.get("messages", [])

        # Time-based memory window: include only recent messages.
        effective_window_hours = (
            window_hours if window_hours is not None else int(getattr(config, "CONTEXT_WINDOW_HOURS", 12) or 12)
        )
        filtered_messages = list(messages)
        if effective_window_hours > 0:
            cutoff = utc_now() - datetime.timedelta(hours=effective_window_hours)
            filtered_messages = []
            for msg in messages:
                ts_raw = msg.get("timestamp")
                # Do not let legacy messages without timestamps bypass the active window.
                if ts_raw is None:
                    continue
                msg_ts = parse_timestamp_utc(
                    ts_raw,
                    fallback=datetime.datetime.fromtimestamp(0, tz=datetime.UTC),
                )
                if msg_ts >= cutoff:
                    filtered_messages.append(msg)

        #  hard cap after time filtering.
        effective_max_messages = int(max_messages or 0)
        if effective_max_messages > 0:
            selected_messages = filtered_messages[-effective_max_messages:]
        else:
            selected_messages = filtered_messages

        # Global safety cap (0 = disabled).
        global_cap = int(getattr(config, "MAX_CONTEXT_MESSAGES_IN_WINDOW", 0) or 0)
        if global_cap > 0 and len(selected_messages) > global_cap:
            selected_messages = selected_messages[-global_cap:]

        # After "release to bot": drop pre-handover messages so GPT starts from a clean window (see set_human_takeover_status release).
        reset_raw = conversation_data.get("ai_context_reset_at")
        if reset_raw is not None:
            try:
                reset_at = parse_timestamp_utc(reset_raw)
                _epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)
                trimmed = []
                for msg in selected_messages:
                    ts_raw = msg.get("timestamp")
                    if ts_raw is None:
                        continue
                    msg_ts = parse_timestamp_utc(ts_raw, fallback=_epoch)
                    if msg_ts >= reset_at:
                        trimmed.append(msg)
                selected_messages = trimmed
                print(
                    f"   📎 ai_context_reset_at applied for conv {conversation_id}: "
                    f"{len(trimmed)} message(s) kept after operator release"
                )
            except Exception as _reset_err:
                print(f"⚠️ ai_context_reset_at filter skipped: {_reset_err}")

        # Convert to OpenAI format
        # Valid OpenAI roles: 'system', 'assistant', 'user', 'function', 'tool'
        openai_messages = []
        for msg in selected_messages:
            original_role = msg.get("role", "user")

            # Map roles to OpenAI-compatible roles
            if original_role == "ai":
                role = "assistant"
            elif original_role == "operator":
                # Treat operator messages as assistant (human staff responding)
                role = "assistant"
            elif original_role in ["user", "assistant", "system", "function", "tool"]:
                role = original_role
            else:
                # Skip unknown roles to prevent API errors
                print(f"⚠️ Skipping message with unknown role: {original_role}")
                continue

            content = msg.get("text", "")
            meta = msg.get("metadata", {}) or {}
            src = meta.get("source", "")
            if src == "smart_message":
                content = f"[Clinic notification we sent to user]\n{content}"
            elif src == "qa_database":
                content = f"[FAQ answer we sent to user]\n{content}"
            openai_messages.append({"role": role, "content": content})

        print(
            f"✅ Fetched {len(openai_messages)} messages from Firestore for conversation {conversation_id} "
            f"(user={used_uid or user_id}, window={effective_window_hours}h, cap={global_cap if global_cap > 0 else 'none'})"
        )
        return openai_messages

    except Exception as e:
        print(f"❌ ERROR fetching conversation history from Firestore: {e}")
        import traceback

        traceback.print_exc()
        return []


async def get_conversation_last_ai_response_at(
    user_id: str, conversation_id: str, alternate_user_id: str | None = None
) -> Any:
    """
    Returns the timestamp of the last AI response for this conversation (from Firestore).
    Used to compute show_greeting: if 12+ hours since last AI reply, show greeting again.
    Returns None if not found or no prior AI response.
    Tries user_id first, then alternate_user_id (e.g. canonical_user_id) if provided.
    """
    db = get_firestore_db()
    if not db or not conversation_id:
        return None
    app_id = "linas-ai-bot-backend"
    for uid in [user_id, alternate_user_id] if alternate_user_id and alternate_user_id != user_id else [user_id]:
        if not uid:
            continue
        conv_ref = (
            db.collection("artifacts")
            .document(app_id)
            .collection("users")
            .document(uid)
            .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
            .document(conversation_id)
        )
        try:
            snap = await asyncio.to_thread(conv_ref.get)
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            raw = data.get("last_ai_response_at")
            if raw is None:
                return None
            return parse_timestamp_utc(raw, fallback=utc_now())
        except Exception as e:
            print(f"⚠️ get_conversation_last_ai_response_at failed for {uid}: {e}")
    return None


async def get_last_bot_message_from_conversation(
    user_id: str, conversation_id: str, alternate_user_id: str | None = None
) -> Any:
    """
    Returns the last message we sent to the user (ai or operator) with text and metadata.
    Used to give GPT context when user replies after a smart message or any notification.
    Returns None if not found.
    """
    db = get_firestore_db()
    if not db or not conversation_id:
        return None
    app_id = "linas-ai-bot-backend"
    for uid in [user_id, alternate_user_id] if alternate_user_id and alternate_user_id != user_id else [user_id]:
        if not uid:
            continue
        conv_ref = (
            db.collection("artifacts")
            .document(app_id)
            .collection("users")
            .document(uid)
            .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
            .document(conversation_id)
        )
        try:
            snap = await asyncio.to_thread(conv_ref.get)
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            messages = data.get("messages", [])
            for msg in reversed(messages):
                role = msg.get("role", "")
                if role in ("ai", "operator"):
                    return {
                        "text": msg.get("text", ""),
                        "metadata": msg.get("metadata", {}),
                        "timestamp": msg.get("timestamp"),
                    }
            return None
        except Exception as e:
            print(f"⚠️ get_last_bot_message_from_conversation failed for {uid}: {e}")
    return None


async def get_last_bot_message_for_gpt_context(
    user_id: str,
    conversation_id: str | None,
    alternate_user_id: str | None = None,
    within_hours: float | None = None,
) -> dict[str, Any] | None:
    """
    Last outbound message for GPT operational context. If the smart message was saved on another
    Firestore thread (identity/query mismatch), still surface it when it is newer than the current
    thread's last bot message. When conversation_id is missing, still returns a recent smart_message
    if any (e.g. new inbound right after restart before conv is resolved).
    """
    effective_within_hours = (
        float(within_hours) if within_hours is not None else float(getattr(config, "CONTEXT_WINDOW_HOURS", 12) or 12)
    )
    canonical = (alternate_user_id or "").strip() or user_id
    smart = await _latest_smart_ai_across_conversations(canonical, within_hours=effective_within_hours)
    if not conversation_id:
        return smart
    cur = await get_last_bot_message_from_conversation(user_id, conversation_id, alternate_user_id)

    def _ts(m: dict | None) -> Any:
        if not m:
            return None
        return parse_timestamp_utc(m.get("timestamp"), fallback=None)

    cutoff = utc_now() - datetime.timedelta(hours=effective_within_hours)
    st, ct = _ts(smart), _ts(cur)
    if st is not None and st < cutoff:
        smart = None
        st = None
    if ct is not None and ct < cutoff:
        cur = None
        ct = None

    if smart and not cur:
        return cast(dict[str, Any] | None, smart)
    if cur and not smart:
        return cast(dict[str, Any] | None, cur)
    if not cur and not smart:
        return None
    if st and ct:
        return cast(dict[str, Any] | None, smart if st > ct else cur)
    if st and not ct:
        return cast(dict[str, Any] | None, smart)
    return cast(dict[str, Any] | None, cur)
