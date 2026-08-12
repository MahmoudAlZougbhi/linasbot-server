"""Human-takeover flags, post-release cooldown, and conversation path updates."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

import config
from services.live_chat_contracts import (
    parse_timestamp_utc,
    utc_now,
)
from utils.phone_utils import is_phone_like_user_id, normalize_phone
from utils.utils_firestore import get_firestore_db
from utils.utils_identity import get_canonical_user_id_and_phone

_log = logging.getLogger(__name__)


def set_post_takeover_escalation_cooldown(user_data: dict) -> None:
    """After release from human queue, suppress AI auto handover (frustration/error paths) for a cooldown window."""
    if not isinstance(user_data, dict):
        return
    try:
        mins = int(getattr(config, "POST_TAKEOVER_ESCALATION_COOLDOWN_MINUTES", 45))
    except (TypeError, ValueError):
        mins = 45
    user_data["post_takeover_escalation_cooldown_until"] = utc_now() + datetime.timedelta(minutes=mins)


def is_post_takeover_escalation_cooldown(user_data: dict) -> bool:
    """True while we should not auto-escalate from handover_degree or GPT error paths."""
    if not isinstance(user_data, dict):
        return False
    until = user_data.get("post_takeover_escalation_cooldown_until")
    if until is None:
        return False
    try:
        if not isinstance(until, datetime.datetime):
            until = parse_timestamp_utc(until)
        return until > utc_now()
    except TypeError:
        return False


def iter_conversation_parent_user_ids_for_firestore(user_id: str) -> list:
    """
    All users/{id}/conversations/... parent IDs that might hold a duplicate doc.
    Matches live_chat_service candidate order (+/- phone) plus normalized phone forms.
    """
    if not user_id:
        return []
    canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
    out: list = []

    def add(x: str) -> None:
        if x and x not in out:
            out.append(x)

    def add_alt_phone(c: str) -> None:
        if not c:
            return
        if c.startswith("+") or (c.isdigit() and len(str(c)) >= 10):
            alt = c[1:] if c.startswith("+") else f"+{c}"
            add(alt)

    add(user_id)
    add(canonical_user_id)
    add_alt_phone(user_id)
    add_alt_phone(canonical_user_id)
    bases = list(out)
    for b in bases:
        if is_phone_like_user_id(b):
            normalized = normalize_phone(b)
            if normalized:
                add(normalized)
                add(normalized.lstrip("+"))
                if normalized.startswith("+961") and len(normalized) > 4:
                    add(normalized[4:])
    return out


def merge_conversation_user_id_variants(*seeds: str) -> list:
    """Union of iter_conversation_parent_user_ids_for_firestore for each non-empty seed, stable order."""
    seen = set()
    merged = []
    for s in seeds:
        if not s:
            continue
        for v in iter_conversation_parent_user_ids_for_firestore(s):
            if v not in seen:
                seen.add(v)
                merged.append(v)
    return merged


async def conversation_any_path_post_release_blocked(
    conversation_id: str, user_id: str, request_user_id: str | None = None
) -> bool:
    """True if any duplicate conversation doc under users/* has an active post-release cooldown."""
    db = get_firestore_db()
    if not db or not conversation_id or not (user_id or request_user_id):
        return False
    app_id_for_firestore = "linas-ai-bot-backend"
    users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
    for vid in merge_conversation_user_id_variants(request_user_id or "", user_id or ""):
        ref = users_coll.document(vid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
        snap = await asyncio.to_thread(ref.get)
        if snap.exists and firestore_post_release_waiting_blocked(snap.to_dict() or {}):
            return True
    return False


async def update_conversation_on_all_existing_paths(
    conversation_id: str,
    user_id: str,
    update_payload: dict,
    request_user_id: str | None = None,
) -> int:
    """Merge-update every users/*/conversations/{conversation_id} that exists. Returns write count."""
    db = get_firestore_db()
    if not db or not conversation_id or not user_id or not update_payload:
        return 0
    app_id_for_firestore = "linas-ai-bot-backend"
    users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")
    variants = merge_conversation_user_id_variants(request_user_id or "", user_id or "")
    n = 0
    for vid in variants:
        ref = users_coll.document(vid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
        snap = await asyncio.to_thread(ref.get)
        if snap.exists:
            try:
                await asyncio.to_thread(ref.update, update_payload)
                n += 1
            except Exception as ex:
                print(
                    f"⚠️ update_conversation_on_all_existing_paths failed users/{vid}/conversations/{conversation_id}: {ex}"
                )
    return n


def firestore_post_release_waiting_blocked(conv_payload: dict) -> bool:
    """
    True if the conversation document forbids re-entering the waiting queue (after release to bot).
    Used to block set_human_takeover_status / direct Firestore handover writes during cooldown.
    """
    if not isinstance(conv_payload, dict):
        return False
    raw = conv_payload.get("post_release_escalation_suppressed_until")
    if raw is None:
        return False
    try:
        return parse_timestamp_utc(raw) > utc_now()
    except Exception:
        return False


def sync_post_release_cooldown_from_conv_payload(user_data: dict, conv_data: dict) -> None:
    """
    Copy post-release escalation cooldown from Firestore conversation doc into user_data.
    Survives dashboard-only release (no prior in-memory takeover flag) and multi-instance workers.
    """
    if not isinstance(user_data, dict) or not isinstance(conv_data, dict):
        return
    raw_until = conv_data.get("post_release_escalation_suppressed_until")
    if raw_until is None:
        return
    try:
        parsed = parse_timestamp_utc(raw_until)
        if parsed > utc_now():
            user_data["post_takeover_escalation_cooldown_until"] = parsed
    except Exception:
        pass


def _clear_takeover_flags_for_user(resolved_user_id: str, raw_user_id: str, canonical_user_id: str) -> None:
    """Clear config.user_in_human_takeover_mode for all user_id variants so release works regardless of message format."""
    variants = {v for v in (resolved_user_id, raw_user_id, canonical_user_id) if v}
    if is_phone_like_user_id(resolved_user_id or raw_user_id):
        normalized = normalize_phone(resolved_user_id or raw_user_id)
        if normalized:
            variants.add(normalized)
            variants.add(normalized.lstrip("+"))
            if normalized.startswith("+961") and len(normalized) > 4:
                variants.add(normalized[4:])  # 3956607
    for v in variants:
        config.user_in_human_takeover_mode.pop(v, None)
        try:
            from services.scale.conversation_state_redis import set_takeover

            set_takeover(v, False)
        except Exception:
            pass


def _build_user_id_variants_for_release(resolved_user_id: str, raw_user_id: str, canonical_user_id: str) -> list:
    """Build all user_id variants that might have a conversation doc (for release - update all paths)."""
    return merge_conversation_user_id_variants(
        raw_user_id or "",
        resolved_user_id or "",
        canonical_user_id or "",
    )


async def set_human_takeover_status(
    user_id: str,
    conversation_id: str,
    status: bool,
    operator_id: str | None = None,
    operator_name: str | None = None,
    request_user_id: str | None = None,
    force_waiting_queue: bool = False,
) -> Any:
    """
    Sets the human takeover status for a specific conversation in Firestore.
    This will control the AI's response for that chat.

    Args:
        user_id: The user's ID (room_id for Qiscus)
        conversation_id: The conversation document ID
        status: True to activate human takeover, False to release
        operator_id:  operator ID who is taking over
        operator_name:  operator name for display to customer
        force_waiting_queue: If True, allow waiting-queue state even when post-release cooldown is active (e.g. /takeover).
    """
    import asyncio

    if not conversation_id:
        print("❌ set_human_takeover_status: missing conversation_id")
        return

    canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
    db = get_firestore_db()
    if not db:
        print("❌ Firestore not initialized. Cannot set human takeover status.")
        return

    app_id_for_firestore = "linas-ai-bot-backend"
    users_coll = db.collection("artifacts").document(app_id_for_firestore).collection("users")

    variants = merge_conversation_user_id_variants(request_user_id or "", user_id or "")
    if not variants:
        print("❌ set_human_takeover_status: no user id variants to search")
        return

    existing = []
    for vid in variants:
        ref = users_coll.document(vid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
        snap = await asyncio.to_thread(ref.get)
        if snap.exists:
            existing.append((vid, ref, snap))

    if not existing:
        raise ValueError(f"Conversation not found (conv={conversation_id}, searched {len(variants)} user id variants)")

    resolved_user_id = existing[0][0]

    try:
        update_data = {"human_takeover_active": status, "last_updated": utc_now()}

        if status and operator_id:
            # Taking over by an assigned operator.
            update_data["operator_id"] = operator_id
            update_data["takeover_time"] = utc_now()
            update_data["status"] = "human"
            update_data["conversation_state"] = "assigned_to_operator"
            if operator_name:
                update_data["operator_name"] = operator_name
                print(f"🔄 Setting conversation status to 'human' for operator takeover by {operator_name}")
            else:
                print("🔄 Setting conversation status to 'human' for operator takeover")
        elif status:
            if not force_waiting_queue:
                for _, _, snap in existing:
                    if firestore_post_release_waiting_blocked(snap.to_dict() or {}):
                        print(
                            f"⚠️ set_human_takeover_status: blocked waiting_human (post_release cooldown on at least one path conv={conversation_id})"
                        )
                        return
            # Human takeover requested but not assigned yet (waiting queue state).
            update_data["operator_id"] = None
            update_data["operator_name"] = None
            update_data["status"] = "waiting_human"
            update_data["conversation_state"] = "waiting_for_operator"
            update_data["human_takeover_requested"] = True
            update_data["escalation_time"] = utc_now()
            print("🔄 Setting conversation status to 'waiting_human' (awaiting operator assignment)")
        elif not status:
            # Releasing - remove operator_id, operator_name and change status back to "active"
            update_data["operator_id"] = None
            update_data["operator_name"] = None
            update_data["release_time"] = utc_now()
            update_data["status"] = "active"
            update_data["conversation_state"] = "bot_active"
            update_data["human_takeover_requested"] = False
            try:
                _cd_mins = int(getattr(config, "POST_TAKEOVER_ESCALATION_COOLDOWN_MINUTES", 45))
            except (TypeError, ValueError):
                _cd_mins = 45
            # Persist cooldown on the doc so any worker / next message applies AI anti-re-escalation
            update_data["post_release_escalation_suppressed_until"] = utc_now() + datetime.timedelta(minutes=_cd_mins)
            # GPT context: only messages at/after this timestamp are sent to the AI (fresh session after operator)
            update_data["ai_context_reset_at"] = utc_now()
            print("🔄 Setting conversation status to 'active' for bot release")

        if status:
            # Clear persisted cooldown when entering takeover again
            update_data["post_release_escalation_suppressed_until"] = None
            update_data["ai_context_reset_at"] = None

        for vid, ref, _ in existing:
            try:
                await asyncio.to_thread(ref.update, update_data)
                if len(existing) > 1:
                    print(f"   ✅ Synced users/{vid}/conversations/{conversation_id}")
            except Exception as path_err:
                print(f"   ⚠️ Failed update users/{vid}/conversations/{conversation_id}: {path_err}")

        if status:
            for vid in variants:
                config.user_in_human_takeover_mode[vid] = True
                try:
                    from services.scale.conversation_state_redis import set_takeover

                    set_takeover(vid, True)
                except Exception:
                    pass
        else:
            _clear_takeover_flags_for_user(resolved_user_id, request_user_id or user_id, canonical_user_id)

        operator_info = f" by operator {operator_name or operator_id}" if operator_id else ""
        print(
            f"✅ Set human takeover status for conversation {conversation_id} (user {resolved_user_id}) to {status}{operator_info} ({len(existing)} doc path(s))."
        )
    except Exception as e:
        print(f"❌ ERROR setting human takeover status for conversation {conversation_id} (user {user_id}): {e}")
        import traceback

        traceback.print_exc()
