"""Live-chat cache/index hooks used when saving conversation messages."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

from firebase_admin import firestore

import config
from services.live_chat_contracts import (
    extract_source_message_id as contract_extract_source_message_id,
)
from services.live_chat_contracts import (
    is_duplicate_message as contract_is_duplicate_message,
)
from services.live_chat_contracts import (
    parse_timestamp_utc,
    utc_now,
)
from utils.utils_firestore import get_firestore_db
from utils.utils_identity import get_canonical_user_id_and_phone
from utils.utils_takeover import (
    firestore_post_release_waiting_blocked,
    merge_conversation_user_id_variants,
)

_log = logging.getLogger(__name__)

MESSAGE_DEDUPE_WINDOW_SECONDS = 20


def _extract_source_message_id(metadata: dict) -> str:
    return contract_extract_source_message_id(metadata)

def _parse_timestamp_for_dedupe(timestamp: Any) -> datetime.datetime:
    return parse_timestamp_utc(timestamp)

def _is_duplicate_message(existing_messages: list, new_message: dict) -> bool:
    return contract_is_duplicate_message(
        existing_messages,
        new_message,
        dedupe_window_seconds=MESSAGE_DEDUPE_WINDOW_SECONDS,
    )

def _message_to_dashboard_format(msg: dict) -> dict:
    """Convert internal message format to dashboard-compatible shape for instant SSE append."""
    if not msg:
        return {}
    ts = msg.get("timestamp")
    if isinstance(ts, datetime.datetime):
        ts_str = ts.isoformat()
    elif ts is not None:
        ts_str = str(ts)
    else:
        ts_str = utc_now().isoformat()
    role = str(msg.get("role", "")).strip().lower()
    meta = msg.get("metadata") or {}
    handled = meta.get("handled_by")
    if not handled:
        handled = "human" if role == "operator" else ("bot" if meta.get("source") == "qa_database" else "ai")
    message_id = msg.get("message_id") or meta.get("message_id") or meta.get("source_message_id") or f"ts_{ts_str}"
    out = {
        "message_id": str(message_id),
        "timestamp": ts_str,
        "is_user": role == "user",
        "content": msg.get("text", ""),
        "text": msg.get("text", ""),
        "type": msg.get("type") or meta.get("type") or "text",
        "handled_by": handled,
        "role": role,
    }
    for key in ("audio_url", "image_url"):
        val = msg.get(key) or meta.get(key)
        if val:
            out[key] = val
    if meta.get("reply_source"):
        out["reply_source"] = meta["reply_source"]
    if meta.get("faq_match"):
        out["metadata"] = out.get("metadata") or {}
        out["metadata"]["faq_match"] = meta["faq_match"]
    return out

async def _update_customer_name_from_external_after_save(
    canonical_user_id: str,
    normalized_phone: str,
    conversation_id: str,
    conversations_collection_for_user: Any,
    user_doc_ref: Any,
) -> Any:
    """Update customer name from CRM in background so user message can save+broadcast first."""
    try:
        from services.customer_identity_service import resolve_customer_from_external

        external = await resolve_customer_from_external(normalized_phone)
        customer_name = (external.get("name") or "") if external.get("exists") else ""
        external_id = external.get("external_id")
        if customer_name:
            config.user_names[canonical_user_id] = customer_name
        doc_ref = conversations_collection_for_user.document(conversation_id)
        doc_snap = await asyncio.to_thread(doc_ref.get)
        if doc_snap.exists:
            doc_data = doc_snap.to_dict() or {}
            customer_info = dict(doc_data.get("customer_info") or {})
            customer_info["name"] = customer_name
            customer_info["last_updated"] = utc_now()
            customer_info["crm_customer_exists"] = external.get("exists", False)
            await asyncio.to_thread(doc_ref.update, {"customer_info": customer_info})
            _refresh_live_chat_index_async(canonical_user_id, conversation_id)
        if customer_name or external_id is not None:
            update_data = {"last_activity": utc_now(), "name": customer_name}
            if external_id is not None:
                update_data["external_id"] = external_id
            await asyncio.to_thread(user_doc_ref.update, update_data)
        _log.info(
            "Background customer name updated for %s: name=%s", canonical_user_id, customer_name or "(phone only)"
        )
    except Exception as e:
        _log.warning("Background customer name update failed: %s", e)

def _invalidate_live_chat_cache() -> None:
    try:
        from services.live_chat_service import live_chat_service

        live_chat_service.invalidate_cache()
    except Exception:
        pass

def _refresh_live_chat_index_async(user_id: str, conversation_id: str) -> None:
    """Fire-and-forget index refresh so new messages populate live_chat_index."""
    try:
        canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
        from services.live_chat_service import live_chat_service

        print(f"🔄 [index-refresh] enqueue refresh user={canonical_user_id} conv={conversation_id}")
        asyncio.create_task(live_chat_service._refresh_index_for_conversation(canonical_user_id, conversation_id))
    except Exception as e:
        print(f"⚠️ [index-refresh] enqueue failed for user={user_id} conv={conversation_id}: {e}")

def _conversation_state_fields_changed(doc_before: Any, update_payload: dict) -> bool:
    """True if save payload changes fields that drive live_chat_index / dashboard tabs."""
    if doc_before is None:
        return True
    if not isinstance(doc_before, dict):
        return True
    for key in ("human_takeover_active", "conversation_state", "operator_id", "status"):
        if key not in update_payload:
            continue
        if doc_before.get(key) != update_payload.get(key):
            return True
    return False

async def _resolve_conversation_doc_for_save(
    db: Any,
    app_id_for_firestore: str,
    conversation_id: str,
    raw_user_id: str,
    canonical_user_id: str,
) -> Any:
    """
    Find users/*/conversations/{conversation_id} across the same id variants as handover/release.
    If several duplicates exist, prefer the doc that looks released to bot (hta False / post_release cooldown)
    so we do not append to a stale waiting copy after dashboard release.
    Returns (doc_ref, snapshot, conversations_collection) or (None, None, None) if missing everywhere.
    """
    if not conversation_id:
        return None, None, None
    users_root = db.collection("artifacts").document(app_id_for_firestore).collection("users")
    found: list = []
    for vid in merge_conversation_user_id_variants(raw_user_id or "", canonical_user_id or ""):
        if not vid:
            continue
        coll = users_root.document(vid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
        ref = coll.document(conversation_id)
        snap = await asyncio.to_thread(ref.get)
        if snap.exists:
            found.append((ref, snap, coll))

    if not found:
        return None, None, None
    if len(found) == 1:
        return found[0]

    def _pick_score(item: Any) -> Any:
        _, snap, _ = item
        d = snap.to_dict() or {}
        hta = d.get("human_takeover_active")
        if hta is False:
            tier = 3
        elif hta is True:
            tier = 1
        else:
            tier = 2
        cooldown = 1 if firestore_post_release_waiting_blocked(d) else 0
        return (tier, cooldown)

    best = max(found, key=_pick_score)
    return best

async def _ensure_live_chat_index_after_save(
    canonical_user_id: str,
    conversation_id: str,
    doc_before: dict[str, Any] | None,
    update_payload: dict,
    *,
    force_await: bool = False,
) -> Any:
    """
    When takeover/state fields change, await index sync so unified tabs do not flicker
    (otherwise the UI reads stale live_chat_index until the background task finishes).
    """
    try:
        from services.live_chat_service import live_chat_service

        must_await = force_await or _conversation_state_fields_changed(doc_before or {}, update_payload or {})
        if must_await:
            await asyncio.wait_for(
                live_chat_service._refresh_index_for_conversation(canonical_user_id, conversation_id),
                timeout=20.0,
            )
        else:
            _refresh_live_chat_index_async(canonical_user_id, conversation_id)
    except Exception as e:
        print(f"⚠️ [index-refresh] after save conv={conversation_id}: {e}")
        _refresh_live_chat_index_async(canonical_user_id, conversation_id)

async def _propagate_takeover_state_to_sibling_conversation_docs(
    db: Any,
    app_id_for_firestore: str,
    conversation_id: str,
    raw_user_id: str,
    canonical_user_id: str,
    primary_doc_ref: Any,
    update_payload: dict,
) -> Any:
    """
    save_conversation_message updates only one users/{variant}/conversations/{id} document.
    Duplicate docs under other id variants (phone formats) can keep human_takeover_active=True
    and keep the chat appearing in "waiting". Merge canonical takeover fields onto siblings.
    """
    if not db or not conversation_id or not primary_doc_ref or not update_payload:
        return
    sync_keys = (
        "human_takeover_active",
        "conversation_state",
        "status",
        "operator_id",
        "post_release_escalation_suppressed_until",
        "ai_context_reset_at",
        "human_takeover_requested",
    )
    sub = {k: update_payload[k] for k in sync_keys if k in update_payload}
    if "human_takeover_active" not in sub:
        return
    # Cooldown / GPT reset often exist only on the doc we wrote — copy from primary so siblings match.
    if sub.get("human_takeover_active") is False:
        try:
            primary_snap = await asyncio.to_thread(primary_doc_ref.get)
            if primary_snap.exists:
                pd = primary_snap.to_dict() or {}
                for k in ("post_release_escalation_suppressed_until", "ai_context_reset_at"):
                    if k in pd and pd[k] is not None:
                        sub[k] = pd[k]
        except Exception as e:
            _log.debug("propagate_takeover primary re-read failed: %s", e)

    users_root = db.collection("artifacts").document(app_id_for_firestore).collection("users")
    primary_path = primary_doc_ref.path
    any_updated = False
    for vid in merge_conversation_user_id_variants(raw_user_id or "", canonical_user_id or ""):
        if not vid:
            continue
        coll = users_root.document(vid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
        ref = coll.document(conversation_id)
        if ref.path == primary_path:
            continue
        try:
            snap = await asyncio.to_thread(ref.get)
            if not snap.exists:
                continue
            d = snap.to_dict() or {}
            mismatch = False
            for k, v in sub.items():
                if v is None:
                    continue
                if d.get(k) != v:
                    mismatch = True
                    break
            if not mismatch:
                continue
            await asyncio.to_thread(ref.update, sub)
            any_updated = True
            _log.info(
                "propagate_takeover aligned sibling conv=%s user_variant=%s",
                conversation_id,
                vid,
            )
        except Exception as ex:
            _log.warning(
                "propagate_takeover failed conv=%s path=%s: %s",
                conversation_id,
                getattr(ref, "path", "?"),
                ex,
            )
    if any_updated:
        _invalidate_live_chat_cache()

async def _resolve_latest_conversation_id(conversations_collection_for_user: Any) -> str | None:
    """
    Prefer the conversation with the newest last_updated. Uses an ordered query when possible;
    if that fails (missing index, etc.), falls back to a full collection scan.
    """
    try:
        query = conversations_collection_for_user.order_by("last_updated", direction=firestore.Query.DESCENDING).limit(
            1
        )
        docs = await asyncio.to_thread(lambda: list(query.stream()))
        if docs:
            return str(docs[0].id)
    except Exception as q_err:
        print(f"⚠️ Could not query conversations by last_updated, scanning: {q_err}")

    try:
        docs = await asyncio.to_thread(lambda: list(conversations_collection_for_user.stream()))
    except Exception as e2:
        print(f"⚠️ Conversation collection stream failed: {e2}")
        return None

    if not docs:
        return None

    best_id = None
    best_ts = None
    for d in docs:
        data = d.to_dict() or {}
        raw = data.get("last_updated") or data.get("last_message_at") or data.get("timestamp")
        ts = parse_timestamp_utc(raw, fallback=None) if raw is not None else None
        if ts is None:
            continue
        if best_ts is None or ts > best_ts:
            best_ts = ts
            best_id = d.id

    if best_id:
        return str(best_id)

    return str(
        max(
            docs,
            key=lambda d: len((d.to_dict() or {}).get("messages") or []),
        ).id
    )

async def _latest_smart_ai_across_conversations(canonical_user_id: str, within_hours: float = 72) -> dict | None:
    """Newest ai message with metadata.source == smart_message across all threads for this user."""
    db = get_firestore_db()
    if not db or not canonical_user_id:
        return None
    app_id = "linas-ai-bot-backend"
    coll = (
        db.collection("artifacts")
        .document(app_id)
        .collection("users")
        .document(canonical_user_id)
        .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
    )
    cutoff = utc_now() - datetime.timedelta(hours=within_hours)
    best = None
    best_ts = None
    try:
        docs = await asyncio.to_thread(lambda: list(coll.stream()))
    except Exception as e:
        print(f"⚠️ _latest_smart_ai_across_conversations: {e}")
        return None

    for doc in docs:
        data = doc.to_dict() or {}
        for msg in data.get("messages") or []:
            if msg.get("role") != "ai":
                continue
            meta = msg.get("metadata") or {}
            if meta.get("source") != "smart_message":
                continue
            ts = parse_timestamp_utc(msg.get("timestamp"), fallback=None)
            if ts is None:
                ts = utc_now()
            if ts < cutoff:
                continue
            if best_ts is None or ts > best_ts:
                best_ts = ts
                best = {
                    "text": msg.get("text", ""),
                    "metadata": meta,
                    "timestamp": msg.get("timestamp"),
                }
    return best
