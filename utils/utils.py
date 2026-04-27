# utils.py
import re
import json
import os
import uuid
import datetime
import logging
import asyncio
from typing import Any, Optional
from collections import deque
from difflib import SequenceMatcher

import config
from prompt_templates import (
    DEFAULT_SYSTEM_PROMPT_TEMPLATE,
    GENDER_INSTRUCTION_TOKEN,
    KNOWLEDGE_SECTION_TOKEN,
    OPERATIONAL_BLOCK_TOKEN,
    QA_REFERENCE_BLOCK_TOKEN,
)
from utils.phone_utils import normalize_phone, is_phone_like_user_id
from openai import AsyncOpenAI
from services.live_chat_contracts import (
    extract_source_message_id as contract_extract_source_message_id,
    is_duplicate_message as contract_is_duplicate_message,
    normalize_message as contract_normalize_message,
    parse_timestamp_utc,
    utc_now,
)

# NEW: Firebase Admin SDK Imports
import firebase_admin
from firebase_admin import credentials, firestore

# Global Firestore DB instance
_firestore_db = None
_firestore_init_done = False


def initialize_firestore():
    """
    Initializes Firebase Admin SDK and Firestore client.
    This should be called once at application startup.
    """
    import time
    global _firestore_db, _firestore_init_done
    t0 = time.monotonic()

    def _elapsed():
        return time.monotonic() - t0

    try:
        print(f"[auth:Firestore] initialize_firestore ENTRY t=0.00s", flush=True)

        # Check if Firebase Admin SDK is already initialized
        if not firebase_admin._apps:
            # Get the service account key path from environment
            service_account_key_path = os.getenv('FIRESTORE_SERVICE_ACCOUNT_KEY_PATH', 'data/firebase_data.json')
            print(f"[auth:Firestore] step 1: key_path={service_account_key_path} exists={os.path.exists(service_account_key_path)} t={_elapsed():.3f}s", flush=True)

            if not os.path.exists(service_account_key_path):
                print(f"❌ Firebase service account key file not found at: {service_account_key_path}")
                print("🔧 Firestore disabled - chat history won't be saved.")
                _firestore_db = None
                return

            # Load service account to log project config (no secrets)
            with open(service_account_key_path, 'r') as f:
                service_account = json.load(f)
            project_id = service_account.get('project_id', '?')
            storage_bucket = service_account.get('storageBucket')
            client_email = service_account.get('client_email', '?')
            print(f"[auth:Firestore] step 2: project_id={project_id} client_email={client_email} t={_elapsed():.3f}s", flush=True)

            # Initialize Firebase Admin SDK with service account credentials
            cred = credentials.Certificate(service_account_key_path)
            print(f"[auth:Firestore] step 3: credentials.Certificate done t={_elapsed():.3f}s", flush=True)

            options = {}
            if storage_bucket:
                options['storageBucket'] = storage_bucket

            firebase_admin.initialize_app(cred, options)
            print(f"[auth:Firestore] step 4: firebase_admin.initialize_app done t={_elapsed():.3f}s", flush=True)
            if storage_bucket:
                print(f"📦 Storage bucket configured: {storage_bucket}")
        else:
            print(f"[auth:Firestore] Firebase Admin already initialized, skipping init t={_elapsed():.3f}s", flush=True)

        # Initialize Firestore client (lazy - no network until first op)
        _firestore_db = firestore.client()
        _firestore_init_done = True
        print(f"[auth:Firestore] step 5: firestore.client() done t={_elapsed():.3f}s (first network op will happen on first query)", flush=True)
        print("✅ Firestore client initialized successfully!")

    except Exception as e:
        print(f"❌ ERROR initializing Firestore after {_elapsed():.3f}s: {e}")
        print("🔧 Firestore disabled - chat history won't be saved.")
        print("💡 To fix this:")
        print("   1. Go to: https://console.cloud.google.com/datastore/setup?project=linas-ai-bot")
        print("   2. Create a Firestore database in Native mode")
        print("   3. Or update the project ID in firebase_data.json")
        _firestore_db = None
        import traceback
        traceback.print_exc()


def get_firestore_db():
    """Returns the initialized Firestore client instance."""
    if _firestore_db is None:
        print("[auth:Firestore] get_firestore_db: triggering initialize_firestore (lazy init)", flush=True)
        initialize_firestore()
    return _firestore_db


_PHONE_ROOM_MAPPING_CACHE = {"mtime": None, "room_to_phone": {}}
MESSAGE_DEDUPE_WINDOW_SECONDS = 20
_log = logging.getLogger(__name__)


def get_canonical_user_id_and_phone(user_id: str, phone_number: str = None) -> tuple:
    """
    Return (canonical_user_id, normalized_phone) for Firestore and identity.
    - If we have a real phone (from phone_number or user_id when phone-like), canonical_user_id = normalized_phone (E.164).
    - Otherwise canonical_user_id = user_id (e.g. room_id). normalized_phone may be "".
    """
    raw_phone = phone_number or (user_id if is_phone_like_user_id(user_id) else None)
    if not raw_phone or str(raw_phone).strip().startswith("room:"):
        mapped = _resolve_phone_from_room_mapping(user_id)
        raw_phone = mapped or None
    normalized = normalize_phone(raw_phone) if raw_phone else ""
    canonical = normalized if normalized else user_id
    return canonical, normalized


def _normalize_phone_digits(value: str) -> str:
    if value is None:
        return ""
    digits = re.sub(r"\D", "", str(value))
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def _is_placeholder_phone(phone_number: str) -> bool:
    if phone_number is None:
        return True
    value = str(phone_number).strip().lower()
    return (not value) or value in {"unknown", "none", "null"} or value.startswith("room:")


def _clean_phone_for_lookup(phone_number: str) -> str:
    digits = _normalize_phone_digits(phone_number)
    if digits.startswith("961") and len(digits) > 8:
        return digits[3:]
    if digits.startswith("1") and len(digits) == 11:
        return digits[1:]
    return digits


def _load_room_to_phone_mapping() -> dict:
    """
    Load room_id -> phone mapping from data/phone_to_room_mapping.json with mtime cache.
    """
    mapping_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "phone_to_room_mapping.json",
    )

    try:
        mtime = os.path.getmtime(mapping_path)
    except Exception:
        _PHONE_ROOM_MAPPING_CACHE["room_to_phone"] = {}
        _PHONE_ROOM_MAPPING_CACHE["mtime"] = None
        return {}

    if _PHONE_ROOM_MAPPING_CACHE["mtime"] == mtime:
        return _PHONE_ROOM_MAPPING_CACHE["room_to_phone"]

    room_to_phone = {}
    try:
        with open(mapping_path, "r", encoding="utf-8") as mapping_file:
            mapping_data = json.load(mapping_file) or {}

        raw_phone_to_room = mapping_data.get("phone_to_room_mapping", {})
        if isinstance(raw_phone_to_room, dict):
            for raw_phone, raw_room_id in raw_phone_to_room.items():
                room_id = str(raw_room_id).strip()
                phone_value = str(raw_phone).strip()
                if room_id and phone_value:
                    room_to_phone[room_id] = phone_value

        raw_room_to_phone = mapping_data.get("room_to_phone_mapping", {})
        if isinstance(raw_room_to_phone, dict):
            for raw_room_id, raw_phone in raw_room_to_phone.items():
                room_id = str(raw_room_id).strip()
                phone_value = str(raw_phone).strip()
                if room_id and phone_value:
                    room_to_phone[room_id] = phone_value
    except Exception as e:
        print(f"⚠️ Failed loading phone_to_room_mapping.json: {e}")
        room_to_phone = {}

    _PHONE_ROOM_MAPPING_CACHE["room_to_phone"] = room_to_phone
    _PHONE_ROOM_MAPPING_CACHE["mtime"] = mtime
    return room_to_phone


def _resolve_phone_from_room_mapping(user_id: str) -> str:
    room_to_phone = _load_room_to_phone_mapping()
    return room_to_phone.get(str(user_id).strip(), "")


def persist_room_to_phone_mapping(room_id: str, phone: str) -> None:
    """
    Persist room_id -> phone to data/phone_to_room_mapping.json so future requests
    with room_id (e.g. from Qiscus) resolve to the same canonical user. Prevents
    duplicate conversations when provider sends room_id instead of phone.
    """
    if not room_id or not phone or str(phone).strip().startswith("room:"):
        return
    room_id = str(room_id).strip()
    phone = str(phone).strip()
    if not room_id or not phone:
        return
    mapping_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "phone_to_room_mapping.json",
    )
    try:
        data = {}
        if os.path.exists(mapping_path):
            with open(mapping_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        phone_to_room = dict(data.get("phone_to_room_mapping") or {})
        room_to_phone = dict(data.get("room_to_phone_mapping") or {})
        if phone_to_room.get(phone) == room_id and room_to_phone.get(room_id) == phone:
            return
        phone_to_room[phone] = room_id
        room_to_phone[room_id] = phone
        data["phone_to_room_mapping"] = phone_to_room
        data["room_to_phone_mapping"] = room_to_phone
        data.setdefault("notes", "Auto-persisted room<->phone for identity deduplication")
        os.makedirs(os.path.dirname(mapping_path), exist_ok=True)
        with open(mapping_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _PHONE_ROOM_MAPPING_CACHE["mtime"] = None
        _log.info("Persisted room_to_phone room_id=%s phone=%s", room_id, phone)
    except Exception as e:
        _log.warning("Failed to persist room_to_phone mapping: %s", e)


def _extract_source_message_id(metadata: dict) -> str:
    return contract_extract_source_message_id(metadata)


def _parse_timestamp_for_dedupe(timestamp) -> datetime.datetime:
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
    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else (str(ts) if ts else utc_now().isoformat())
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
    conversations_collection_for_user,
    user_doc_ref,
):
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
        _log.info("Background customer name updated for %s: name=%s", canonical_user_id, customer_name or "(phone only)")
    except Exception as e:
        _log.warning("Background customer name update failed: %s", e)


def _invalidate_live_chat_cache():
    try:
        from services.live_chat_service import live_chat_service
        live_chat_service.invalidate_cache()
    except Exception:
        pass


def _refresh_live_chat_index_async(user_id: str, conversation_id: str):
    """Fire-and-forget index refresh so new messages populate live_chat_index."""
    try:
        canonical_user_id, _ = get_canonical_user_id_and_phone(user_id)
        from services.live_chat_service import live_chat_service
        print(f"🔄 [index-refresh] enqueue refresh user={canonical_user_id} conv={conversation_id}")
        asyncio.create_task(live_chat_service._refresh_index_for_conversation(canonical_user_id, conversation_id))
    except Exception as e:
        print(f"⚠️ [index-refresh] enqueue failed for user={user_id} conv={conversation_id}: {e}")


def _conversation_state_fields_changed(doc_before, update_payload: dict) -> bool:
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
    db,
    app_id_for_firestore: str,
    conversation_id: str,
    raw_user_id: str,
    canonical_user_id: str,
):
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

    def _pick_score(item):
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
    doc_before: dict,
    update_payload: dict,
    *,
    force_await: bool = False,
):
    """
    When takeover/state fields change, await index sync so unified tabs do not flicker
    (otherwise the UI reads stale live_chat_index until the background task finishes).
    """
    try:
        from services.live_chat_service import live_chat_service
        must_await = force_await or _conversation_state_fields_changed(
            doc_before or {}, update_payload or {}
        )
        if must_await:
            await asyncio.wait_for(
                live_chat_service._refresh_index_for_conversation(
                    canonical_user_id, conversation_id
                ),
                timeout=20.0,
            )
        else:
            _refresh_live_chat_index_async(canonical_user_id, conversation_id)
    except Exception as e:
        print(f"⚠️ [index-refresh] after save conv={conversation_id}: {e}")
        _refresh_live_chat_index_async(canonical_user_id, conversation_id)


async def _propagate_takeover_state_to_sibling_conversation_docs(
    db,
    app_id_for_firestore: str,
    conversation_id: str,
    raw_user_id: str,
    canonical_user_id: str,
    primary_doc_ref,
    update_payload: dict,
):
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


async def _resolve_latest_conversation_id(conversations_collection_for_user) -> Optional[str]:
    """
    Prefer the conversation with the newest last_updated. Uses an ordered query when possible;
    if that fails (missing index, etc.), falls back to a full collection scan.
    """
    try:
        query = conversations_collection_for_user.order_by(
            "last_updated", direction=firestore.Query.DESCENDING
        ).limit(1)
        docs = await asyncio.to_thread(lambda: list(query.stream()))
        if docs:
            return docs[0].id
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
        return best_id

    return max(
        docs,
        key=lambda d: len((d.to_dict() or {}).get("messages") or []),
    ).id


async def _latest_smart_ai_across_conversations(
    canonical_user_id: str, within_hours: float = 72
) -> Optional[dict]:
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


async def save_conversation_message_to_firestore(user_id: str, role: str, text: str, conversation_id: str = None, user_name: str = None, phone_number: str = None, metadata: dict = None):
    """
    Saves a message (user or bot) to Firestore.
    If conversation_id is provided, appends to existing conversation.
    Otherwise, creates a new conversation.

    Args:
        user_id: The user's WhatsApp ID (could be room_id for Qiscus or phone for others)
        role: 'user' or 'ai' or 'operator'
        text: The message text
        conversation_id: Optional conversation ID. If None, creates a new conversation.
        user_name: Optional user name to save with the conversation
        phone_number: Optional actual phone number (for Qiscus where user_id is room_id)
        metadata: Optional metadata dict (e.g., operator_id, handled_by)
    """
    import asyncio

    def _compute_conversation_state(human_takeover: bool, operator_id_val: Any, status_val: str) -> str:
        if status_val == "archived":
            return "archived"
        if status_val == "resolved":
            return "resolved"
        if human_takeover:
            return "assigned_to_operator" if operator_id_val else "waiting_for_operator"
        return "bot_active"

    # In-memory transcript for GPT (always, including when tests skip Firestore).
    append_turn_to_user_context_memory(user_id, role, text)

    # Check if we're in testing mode - skip Firebase saving for tests
    if hasattr(config, 'TESTING_MODE') and config.TESTING_MODE:
        print(f"🧪 TESTING MODE: Skipping Firebase save for user {user_id}, role {role}")
        return

    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Skipping conversation save.")
        return

    # Use a fixed string for the backend's app ID in Firestore path for consistency.
    app_id_for_firestore = "linas-ai-bot-backend"

    # ✅ FIX: Resolve canonical + refs FIRST (can work with phone_number=None).
    # Then resolve phone from conversation/user if not provided.
    canonical_user_id, normalized_phone = get_canonical_user_id_and_phone(user_id, phone_number)
    user_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(canonical_user_id)
    conversations_collection_for_user = user_doc_ref.collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)

    # Resolve phone_number using fallback chain if not provided.
    # Priority: 1) provided 2) existing conversation 3) user document 4) room mapping 5) user_id fallback
    if not phone_number:
        # Try to get phone from existing conversation
        if conversation_id:
            try:
                existing_conv_ref = conversations_collection_for_user.document(conversation_id)
                existing_conv_snap = await asyncio.to_thread(existing_conv_ref.get)
                if existing_conv_snap.exists:
                    existing_phone = existing_conv_snap.to_dict().get('customer_info', {}).get('phone_full')
                    if existing_phone:
                        phone_number = existing_phone
            except Exception as e:
                print(f"⚠️ Could not retrieve phone from conversation: {e}")

        if not phone_number:
            try:
                user_doc_check = await asyncio.to_thread(user_doc_ref.get)
                if user_doc_check.exists:
                    existing_phone = user_doc_check.to_dict().get('phone_full')
                    if existing_phone:
                        phone_number = existing_phone
            except Exception:
                pass

        if not phone_number:
            mapped_phone = _resolve_phone_from_room_mapping(user_id)
            if mapped_phone:
                phone_number = mapped_phone

        if not phone_number:
            is_likely_phone = (user_id.startswith('+961') or
                              user_id.startswith('961') or
                              (user_id.isdigit() and user_id.startswith('7') and len(user_id) <= 8))
            is_likely_room_id = (user_id.isdigit() and len(user_id) >= 8 and not user_id.startswith('7'))

            if is_likely_room_id or (user_id.isdigit() and len(user_id) >= 9):
                phone_number = f"room:{user_id}"
            else:
                phone_number = user_id

        # Re-resolve canonical if we found phone (for E.164 normalization)
        if phone_number and phone_number != f"room:{user_id}":
            canonical_user_id, normalized_phone = get_canonical_user_id_and_phone(user_id, phone_number)
            user_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(canonical_user_id)
            conversations_collection_for_user = user_doc_ref.collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)

    _log.info(
        "identity raw_phone=%s normalized_phone=%s canonical_user_id=%s user_id_arg=%s",
        phone_number, normalized_phone, canonical_user_id, user_id,
    )

    placeholder_phone = _is_placeholder_phone(phone_number)
    clean_phone = _clean_phone_for_lookup(phone_number)

    # For "user" role: save + broadcast FIRST so message appears instantly in Live Chat; resolve CRM name in background.
    customer_name = user_name or config.user_names.get(canonical_user_id) or config.user_names.get(user_id)
    external_id = None
    defer_external_for_speed = role == "user" and normalized_phone
    if normalized_phone and not defer_external_for_speed:
        try:
            from services.customer_identity_service import resolve_customer_from_external
            external = await resolve_customer_from_external(normalized_phone)
            _log.info(
                "external_lookup normalized_phone=%s exists=%s name=%s external_id=%s",
                normalized_phone, external.get("exists"), external.get("name"), external.get("external_id"),
            )
            if external.get("exists") and external.get("name"):
                customer_name = external["name"]
                config.user_names[canonical_user_id] = customer_name
            else:
                customer_name = customer_name or ""
            external_id = external.get("external_id")
        except Exception as e:
            _log.warning("External resolve failed for %s: %s; using unknown/phone only", normalized_phone, e)
            customer_name = customer_name or ""
    if customer_name is None:
        customer_name = ""
    if not customer_name and not normalized_phone:
        customer_name = "Unknown Customer"

    # Ensure the user document exists (create if it doesn't)
    # Get current gender and greeting stage for persistence (by canonical id)
    current_gender = config.user_gender.get(canonical_user_id, "") or config.user_gender.get(user_id, "")
    current_greeting_stage = config.user_greeting_stage.get(canonical_user_id, 0) or config.user_greeting_stage.get(user_id, 0)

    # Store E.164 for consistency when we have it
    effective_phone_full = normalized_phone if normalized_phone else phone_number
    effective_phone_clean = _clean_phone_for_lookup(effective_phone_full) if not placeholder_phone else clean_phone

    # ✅ Use asyncio.to_thread to prevent blocking
    user_doc = await asyncio.to_thread(user_doc_ref.get)
    if not user_doc.exists:
        user_doc_payload = {
            "user_id": canonical_user_id,
            "name": customer_name,
            "gender": current_gender,
            "greeting_stage": current_greeting_stage,
            "created_at": utc_now(),
            "last_activity": utc_now()
        }
        if not placeholder_phone:
            user_doc_payload["phone_full"] = effective_phone_full
            user_doc_payload["phone_clean"] = effective_phone_clean
        if normalized_phone:
            user_doc_payload["normalized_phone"] = normalized_phone
        if external_id:
            user_doc_payload["external_id"] = external_id
        await asyncio.to_thread(user_doc_ref.set, user_doc_payload)
        _log.info("identity created new user doc canonical_user_id=%s", canonical_user_id)
    else:
        # Update last activity and phone info
        update_data = {
            "last_activity": utc_now(),
            "name": customer_name
        }
        if not placeholder_phone:
            update_data["phone_full"] = effective_phone_full
            update_data["phone_clean"] = effective_phone_clean
        if normalized_phone:
            update_data["normalized_phone"] = normalized_phone
        if external_id:
            update_data["external_id"] = external_id
        if current_gender:
            update_data["gender"] = current_gender
        if current_greeting_stage > 0:
            update_data["greeting_stage"] = current_greeting_stage
        await asyncio.to_thread(user_doc_ref.update, update_data)
        _log.info("identity updated existing user doc canonical_user_id=%s", canonical_user_id)
    
    # Prepare customer info to save (including gender for persistence)
    user_gender_value = config.user_gender.get(canonical_user_id, "") or config.user_gender.get(user_id, "")
    user_greeting_stage_value = config.user_greeting_stage.get(canonical_user_id, 0) or config.user_greeting_stage.get(user_id, 0)

    existing_user_data = user_doc.to_dict() if user_doc.exists else {}
    if placeholder_phone:
        existing_phone = existing_user_data.get("phone_full")
        if existing_phone and not _is_placeholder_phone(existing_phone):
            effective_phone_full = existing_phone
            effective_phone_clean = _clean_phone_for_lookup(existing_phone)

    user_data = config.user_data_whatsapp.get(canonical_user_id) or config.user_data_whatsapp.get(user_id) or {}
    crm_exists = user_data.get("crm_customer_exists")
    customer_info = {
        "phone_full": effective_phone_full,
        "phone_clean": effective_phone_clean,
        "normalized_phone": normalized_phone or None,
        "name": customer_name,
        "gender": user_gender_value,
        "greeting_stage": user_greeting_stage_value,
        "last_updated": utc_now(),
    }
    if crm_exists is not None:
        customer_info["crm_customer_exists"] = bool(crm_exists)

    def _build_message_data() -> dict:
        safe_text = text if isinstance(text, str) else str(text or "")
        detected_language = detect_language(safe_text)["language"]
        normalized_metadata = dict(metadata or {})
        source_message_id = _extract_source_message_id(normalized_metadata)
        if source_message_id:
            normalized_metadata["source_message_id"] = source_message_id

        payload = contract_normalize_message({
            "role": role,
            "text": safe_text,
            "timestamp": utc_now(),
            "language": detected_language,
            "metadata": normalized_metadata,
        })
        # Stable unique message_id: use source_message_id from webhook when available, else generate
        if source_message_id:
            payload["message_id"] = str(source_message_id)
        else:
            payload["message_id"] = f"msg_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        if "metadata" not in payload:
            payload["metadata"] = {}
        payload["metadata"]["message_id"] = payload["message_id"]
        return payload

    saved_conv_id = None  # for deferred external name update (user role)
    try:
        if conversation_id:
            # Resolve doc across all user id variants (same as release/handover) — avoid stale duplicate path
            doc_ref, doc_snap, coll_found = await _resolve_conversation_doc_for_save(
                db,
                app_id_for_firestore,
                conversation_id,
                user_id,
                canonical_user_id,
            )
            if coll_found is not None:
                conversations_collection_for_user = coll_found

            if doc_snap and doc_snap.exists:
                saved_conv_id = conversation_id
                doc_data = doc_snap.to_dict() or {}
                current_messages = doc_data.get("messages", [])
                message_data = _build_message_data()
                is_smart_source = (message_data.get("metadata", {}) or {}).get("source") == "smart_message"

                if _is_duplicate_message(current_messages, message_data):
                    print(f"🔁 Duplicate message skipped for conversation {conversation_id}")
                    _invalidate_live_chat_cache()
                    return

                if _is_placeholder_phone(customer_info.get("phone_full")):
                    existing_customer_info = doc_data.get("customer_info", {}) or {}
                    existing_phone = existing_customer_info.get("phone_full")
                    if existing_phone and not _is_placeholder_phone(existing_phone):
                        customer_info["phone_full"] = existing_phone
                        customer_info["phone_clean"] = _clean_phone_for_lookup(existing_phone)

                current_messages.append(message_data)
                previous_state = doc_data.get("conversation_state")
                unread_before = int(doc_data.get("unread_count") or 0)
                new_unread = unread_before
                if role == "user":
                    new_unread = unread_before + 1
                elif role == "operator":
                    new_unread = 0

                update_payload = {
                    "messages": current_messages,
                    "customer_info": customer_info,
                    "last_updated": utc_now(),
                    "last_message_text": message_data.get("text", ""),
                    "last_message_at": message_data.get("timestamp") or utc_now(),
                    "unread_count": new_unread,
                }
                if role == "ai":
                    update_payload["last_ai_response_at"] = message_data.get("timestamp") or utc_now()
                if not is_smart_source:
                    # human_takeover_active is source of truth; only infer from status when field is missing (legacy)
                    existing_takeover = bool(doc_data.get("human_takeover_active", False))
                    if not existing_takeover and "human_takeover_active" not in doc_data and (
                        doc_data.get("status") == "waiting_human"
                        or doc_data.get("conversation_state") == "waiting_for_operator"
                    ):
                        existing_takeover = True
                    # After release: doc has post_release window — never re-open waiting from stale status fields
                    if firestore_post_release_waiting_blocked(doc_data):
                        existing_takeover = False
                    existing_operator = doc_data.get("operator_id")
                    if existing_takeover:
                        update_payload.update({
                            "status": "human" if existing_operator else "waiting_human",
                            "human_takeover_active": True,
                            "operator_id": existing_operator,
                        })
                    else:
                        update_payload.update({
                            "status": "active",
                            "human_takeover_active": False,
                            "operator_id": None,
                        })
                # Canonical conversation_state for index
                # When is_smart_source: never leave users stuck in human takeover (waiting OR stale operator) —
                # otherwise handle_message only sends handoff/waiting lines and the AI never replies to template replies.
                if is_smart_source:
                    if firestore_post_release_waiting_blocked(doc_data):
                        update_payload.update({
                            "conversation_state": "bot_active",
                            "human_takeover_active": False,
                            "status": "active",
                            "operator_id": None,
                        })
                    elif doc_data.get("human_takeover_active"):
                        update_payload.update({
                            "conversation_state": "bot_active",
                            "human_takeover_active": False,
                            "human_takeover_requested": False,
                            "status": "active",
                            "operator_id": None,
                        })
                    else:
                        update_payload["conversation_state"] = _compute_conversation_state(
                            bool(doc_data.get("human_takeover_active", False)),
                            doc_data.get("operator_id"),
                            doc_data.get("status", "active"),
                        )
                else:
                    update_payload["conversation_state"] = _compute_conversation_state(
                        update_payload.get("human_takeover_active", False),
                        update_payload.get("operator_id"),
                        update_payload.get("status", "active"),
                    )
                if role == "user" and previous_state in {"resolved", "archived"}:
                    update_payload.update({
                        "conversation_state": "bot_active",
                        "status": "active",
                        "human_takeover_active": False,
                        "operator_id": None,
                    })
                await asyncio.to_thread(doc_ref.update, update_payload)
                await _propagate_takeover_state_to_sibling_conversation_docs(
                    db,
                    app_id_for_firestore,
                    conversation_id,
                    user_id,
                    canonical_user_id,
                    doc_ref,
                    update_payload,
                )
                if is_smart_source and role == "ai":
                    _clear_takeover_flags_for_user(canonical_user_id, user_id, canonical_user_id)
                _invalidate_live_chat_cache()
                await _ensure_live_chat_index_after_save(
                    canonical_user_id, conversation_id, doc_data, update_payload
                )
                print(f"✅ Appended {role} message to conversation {conversation_id} (total: {len(current_messages)})")

                # 📡 Broadcast SSE event for real-time dashboard updates (instant WhatsApp-like)
                # Include smart messages so they appear in Live Chat for operators
                try:
                    from modules.live_chat_api import broadcast_sse_event
                    dash_msg = _message_to_dashboard_format(message_data)
                    _log.info("live_chat save_message broadcast conv_id=%s role=%s msg_id=%s",
                        conversation_id, role, dash_msg.get("message_id", ""))
                    asyncio.create_task(broadcast_sse_event("new_message", {
                        "user_id": canonical_user_id,
                        "conversation_id": conversation_id,
                        "role": role,
                        "text": text[:100] + "..." if len(text) > 100 else text,
                        "phone": customer_info.get("phone_full"),
                        "message": dash_msg,
                    }))
                except Exception as sse_err:
                    _log.exception("SSE broadcast error after save: %s", sse_err)
            else:
                # Conversation not found - create new one
                message_data = _build_message_data()

                _, new_doc_ref = await asyncio.to_thread(conversations_collection_for_user.add, {
                    "user_id": canonical_user_id,
                    "customer_info": customer_info,
                    "messages": [message_data],
                    "timestamp": utc_now(),
                    # Smart outbound must stay visible as an active bot thread in Live Chat (not "closed"/archived).
                    "status": "active",
                    "sentiment": "neutral",
                    "human_takeover_active": False,
                    "last_updated": utc_now(),
                    "conversation_state": "bot_active",
                    "last_message_text": message_data.get("text", ""),
                    "last_message_at": message_data.get("timestamp") or utc_now(),
                    "unread_count": 0 if role != "user" else 1,
                })
                saved_conv_id = new_doc_ref.id
                if canonical_user_id not in config.user_data_whatsapp:
                    config.user_data_whatsapp[canonical_user_id] = {}
                config.user_data_whatsapp[canonical_user_id]["current_conversation_id"] = new_doc_ref.id
                _invalidate_live_chat_cache()
                await _ensure_live_chat_index_after_save(
                    canonical_user_id, saved_conv_id, None, {}
                )
                print(f"✅ Created conversation {new_doc_ref.id} for user {canonical_user_id}")
        else:
            # No conversation_id — try to reuse latest conversation first.
            resolved_conversation_id = None

            # 1) Check in-memory cache (by canonical id so same phone = same thread)
            cached_id = config.user_data_whatsapp.get(canonical_user_id, {}).get("current_conversation_id")
            if cached_id:
                try:
                    cached_ref = conversations_collection_for_user.document(cached_id)
                    cached_snap = await asyncio.to_thread(cached_ref.get)
                    if cached_snap.exists:
                        resolved_conversation_id = cached_id
                except Exception:
                    pass

            # 2) Query Firestore for latest conversation (with scan fallback if order_by fails)
            if not resolved_conversation_id:
                resolved_conversation_id = await _resolve_latest_conversation_id(
                    conversations_collection_for_user
                )

            message_data = _build_message_data()
            is_smart_source = (message_data.get("metadata", {}) or {}).get("source") == "smart_message"

            doc_ref = None
            doc_snap = None
            coll_resolved = None
            resolved_exists = False
            if resolved_conversation_id:
                doc_ref, doc_snap, coll_resolved = await _resolve_conversation_doc_for_save(
                    db,
                    app_id_for_firestore,
                    resolved_conversation_id,
                    user_id,
                    canonical_user_id,
                )
                if coll_resolved is not None:
                    conversations_collection_for_user = coll_resolved
                resolved_exists = bool(doc_snap and doc_snap.exists)
                if resolved_conversation_id and not resolved_exists:
                    print(
                        f"⚠️ Resolved conversation {resolved_conversation_id} not found on any user path; "
                        f"creating new thread for {canonical_user_id}"
                    )

            if resolved_conversation_id and resolved_exists:
                saved_conv_id = resolved_conversation_id
                doc_data = doc_snap.to_dict() or {}
                current_messages = doc_data.get("messages", [])

                if _is_duplicate_message(current_messages, message_data):
                    print(f"🔁 Duplicate message skipped for conversation {resolved_conversation_id}")
                    _invalidate_live_chat_cache()
                    return

                if _is_placeholder_phone(customer_info.get("phone_full")):
                    existing_customer_info = doc_data.get("customer_info", {}) or {}
                    existing_phone = existing_customer_info.get("phone_full")
                    if existing_phone and not _is_placeholder_phone(existing_phone):
                        customer_info["phone_full"] = existing_phone
                        customer_info["phone_clean"] = _clean_phone_for_lookup(existing_phone)

                current_messages.append(message_data)
                prev_state = doc_data.get("conversation_state")
                unread_before = int(doc_data.get("unread_count") or 0)
                new_unread = unread_before
                if role == "user":
                    new_unread = unread_before + 1
                elif role == "operator":
                    new_unread = 0

                update_payload = {
                    "messages": current_messages,
                    "customer_info": customer_info,
                    "last_updated": utc_now(),
                    "last_message_text": message_data.get("text", ""),
                    "last_message_at": message_data.get("timestamp") or utc_now(),
                    "unread_count": new_unread,
                }
                # Smart campaign messages should not reopen/take over live conversations.
                if not is_smart_source:
                    # human_takeover_active is source of truth; only infer from status when field is missing (legacy)
                    existing_takeover = bool(doc_data.get("human_takeover_active", False))
                    if not existing_takeover and "human_takeover_active" not in doc_data and (
                        doc_data.get("status") == "waiting_human"
                        or doc_data.get("conversation_state") == "waiting_for_operator"
                    ):
                        existing_takeover = True
                    if firestore_post_release_waiting_blocked(doc_data):
                        existing_takeover = False
                    existing_operator = doc_data.get("operator_id")
                    if existing_takeover:
                        update_payload.update({
                            "status": "human" if existing_operator else "waiting_human",
                            "human_takeover_active": True,
                            "operator_id": existing_operator,
                        })
                    else:
                        update_payload.update({
                            "status": "active",
                            "human_takeover_active": False,
                            "operator_id": None,
                        })
                # When is_smart_source: release human takeover (waiting or assigned) so template replies are handled by AI
                if is_smart_source:
                    if firestore_post_release_waiting_blocked(doc_data):
                        update_payload.update({
                            "conversation_state": "bot_active",
                            "human_takeover_active": False,
                            "status": "active",
                            "operator_id": None,
                        })
                    elif doc_data.get("human_takeover_active"):
                        update_payload.update({
                            "conversation_state": "bot_active",
                            "human_takeover_active": False,
                            "human_takeover_requested": False,
                            "status": "active",
                            "operator_id": None,
                        })
                    else:
                        update_payload["conversation_state"] = _compute_conversation_state(
                            bool(doc_data.get("human_takeover_active", False)),
                            doc_data.get("operator_id"),
                            doc_data.get("status", "active"),
                        )
                else:
                    update_payload["conversation_state"] = _compute_conversation_state(
                        update_payload.get("human_takeover_active", False),
                        update_payload.get("operator_id"),
                        update_payload.get("status", "active"),
                    )
                if role == "user" and prev_state in {"resolved", "archived"}:
                    update_payload.update({
                        "conversation_state": "bot_active",
                        "status": "active",
                        "human_takeover_active": False,
                        "operator_id": None,
                    })
                await asyncio.to_thread(doc_ref.update, update_payload)
                await _propagate_takeover_state_to_sibling_conversation_docs(
                    db,
                    app_id_for_firestore,
                    resolved_conversation_id,
                    user_id,
                    canonical_user_id,
                    doc_ref,
                    update_payload,
                )
                if is_smart_source and role == "ai":
                    _clear_takeover_flags_for_user(canonical_user_id, user_id, canonical_user_id)
                if canonical_user_id not in config.user_data_whatsapp:
                    config.user_data_whatsapp[canonical_user_id] = {}
                config.user_data_whatsapp[canonical_user_id]["current_conversation_id"] = resolved_conversation_id
                _invalidate_live_chat_cache()
                await _ensure_live_chat_index_after_save(
                    canonical_user_id, resolved_conversation_id, doc_data, update_payload
                )
                print(f"✅ Appended {role} message to existing conversation {resolved_conversation_id} for user {canonical_user_id} (total: {len(current_messages)})")

                # 📡 Broadcast SSE event (instant WhatsApp-like) - include smart messages for Live Chat
                try:
                    from modules.live_chat_api import broadcast_sse_event
                    dash_msg = _message_to_dashboard_format(message_data)
                    _log.info("live_chat save_message broadcast conv_id=%s role=%s msg_id=%s",
                        resolved_conversation_id, role, dash_msg.get("message_id", ""))
                    asyncio.create_task(broadcast_sse_event("new_message", {
                        "user_id": canonical_user_id,
                        "conversation_id": resolved_conversation_id,
                        "role": role,
                        "text": text[:100] + "..." if len(text) > 100 else text,
                        "phone": customer_info.get("phone_full"),
                        "message": dash_msg,
                    }))
                except Exception as sse_err:
                    _log.exception("SSE broadcast error: %s", sse_err)
            else:
                # No existing conversation found — create a new one
                _, new_doc_ref = await asyncio.to_thread(conversations_collection_for_user.add, {
                    "user_id": canonical_user_id,
                    "customer_info": customer_info,
                    "messages": [message_data],
                    "timestamp": utc_now(),
                    "status": "active",
                    "sentiment": "neutral",
                    "human_takeover_active": False,
                    "last_updated": utc_now(),
                    "conversation_state": "bot_active",
                    "last_message_text": message_data.get("text", ""),
                    "last_message_at": message_data.get("timestamp") or utc_now(),
                    "unread_count": 0 if role != "user" else 1,
                })
                saved_conv_id = new_doc_ref.id
                if canonical_user_id not in config.user_data_whatsapp:
                    config.user_data_whatsapp[canonical_user_id] = {}
                config.user_data_whatsapp[canonical_user_id]["current_conversation_id"] = new_doc_ref.id
                _invalidate_live_chat_cache()
                await _ensure_live_chat_index_after_save(
                    canonical_user_id, saved_conv_id, None, {}
                )
                print(f"✅ Created conversation {new_doc_ref.id} for user {canonical_user_id}")

                # 📡 Broadcast SSE event for new conversation - include smart messages for Live Chat
                try:
                    from modules.live_chat_api import broadcast_sse_event
                    asyncio.create_task(broadcast_sse_event("new_conversation", {
                        "user_id": canonical_user_id,
                        "conversation_id": new_doc_ref.id,
                        "phone": customer_info.get("phone_full"),
                        "name": customer_name
                    }))
                except Exception:
                    pass

        # Deferred: update customer name from CRM in background so user message already appeared in Live Chat
        if defer_external_for_speed and saved_conv_id and normalized_phone:
            asyncio.create_task(_update_customer_name_from_external_after_save(
                canonical_user_id, normalized_phone, saved_conv_id,
                conversations_collection_for_user, user_doc_ref,
            ))

    except Exception as e:
        print(f"❌ ERROR saving conversation message to Firestore for user {user_id}: {e}")
        import traceback
        traceback.print_exc()


async def update_voice_message_with_transcription(user_id: str, conversation_id: str, audio_url: str, transcribed_text: str, phone_number: str = None):
    """
    Updates a voice message in Firestore after transcription is complete.
    
    This function:
    1. Finds the LAST voice message in the conversation (the one we just saved)
    2. Updates its text field with the transcribed text
    3. Ensures type="voice" and audio_url are at top level for easy dashboard access
    4. Adds transcribed=true flag
    
    Args:
        user_id: The user's WhatsApp ID (room_id for Qiscus)
        conversation_id: The conversation ID to update
        audio_url: The URL of the original audio file
        transcribed_text: The transcribed text from Whisper
        phone_number: Optional phone number for user lookup
    """
    if hasattr(config, 'TESTING_MODE') and config.TESTING_MODE:
        print(f"🧪 TESTING MODE: Skipping Firebase update for voice message")
        return
    
    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Skipping voice message update.")
        return

    app_id_for_firestore = "linas-ai-bot-backend"

    try:
        # Get the conversation document
        doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
        doc_snap = doc_ref.get()

        if not doc_snap.exists:
            print(f"⚠️ Conversation {conversation_id} not found for update")
            return

        doc_data = doc_snap.to_dict()
        current_messages = doc_data.get('messages', [])

        if not current_messages:
            print(f"⚠️ No messages found in conversation {conversation_id}")
            return

        # Find the LAST message that has type="voice" or is the most recent from "user"
        # We look for a message with audio_url or type="voice"
        last_voice_message_index = None
        for i in range(len(current_messages) - 1, -1, -1):  # Search backwards (most recent first)
            msg = current_messages[i]
            if msg.get("type") == "voice" or msg.get("audio_url") == audio_url:
                last_voice_message_index = i
                break

        if last_voice_message_index is None:
            print(f"⚠️ No voice message found in conversation {conversation_id} for audio_url: {audio_url}")
            # As fallback, update the last message if it's from user
            if current_messages and current_messages[-1].get("role") == "user":
                last_voice_message_index = len(current_messages) - 1
            else:
                return

        # Update the voice message with transcribed text
        message = current_messages[last_voice_message_index]
        message["text"] = transcribed_text
        message["type"] = "voice"
        message["audio_url"] = audio_url
        message["transcribed"] = True
        message["transcribed_at"] = utc_now()

        # Update conversation
        doc_ref.update({
            "messages": current_messages,
            "last_updated": utc_now()
        })
        _invalidate_live_chat_cache()

        print(f"✅ Updated voice message in conversation {conversation_id} with transcription")
        print(f"   Text: {transcribed_text[:50]}...")
        print(f"   Audio URL: {audio_url}")

    except Exception as e:
        print(f"❌ ERROR updating voice message in Firestore for user {user_id}: {e}")
        import traceback
        traceback.print_exc()


def convert_webm_to_opus(base64_webm: str) -> tuple[str, str]:
    """
    Convert WebM audio (base64) to OGG/Opus format (base64).
    WhatsApp requires Opus codec wrapped in OGG container (audio/ogg).

    Args:
        base64_webm: Base64-encoded WebM audio data

    Returns:
        Tuple of (base64_ogg_data, file_name_with_ogg_extension)
    """
    try:
        import base64
        import io
        from pydub import AudioSegment
        import time
        
        print(f"🔄 Converting WebM audio to Opus format...")
        
        # Decode base64 to bytes
        webm_bytes = base64.b64decode(base64_webm)
        print(f"   📊 WebM size: {len(webm_bytes)} bytes")
        
        # Load WebM audio with pydub
        webm_audio = AudioSegment.from_file(io.BytesIO(webm_bytes), format="webm")
        print(f"   ✅ WebM loaded: {len(webm_audio)}ms duration, {webm_audio.frame_rate}Hz sample rate")
        
        # Export as OGG with Opus codec (WhatsApp requires Opus in OGG container)
        ogg_buffer = io.BytesIO()
        webm_audio.export(
            ogg_buffer,
            format="ogg",
            codec="libopus",
            bitrate="128k",
            parameters=["-vbr", "on", "-compression_level", "10"]
        )
        ogg_bytes = ogg_buffer.getvalue()
        print(f"   ✅ Converted to OGG/Opus: {len(ogg_bytes)} bytes")

        # Encode back to base64
        base64_ogg = base64.b64encode(ogg_bytes).decode('utf-8')

        # Create new filename with .ogg extension (WhatsApp compatible)
        timestamp = int(time.time())
        file_name = f"voice_{timestamp}.ogg"

        print(f"   ✅ Conversion complete! New file: {file_name}")
        return base64_ogg, file_name
        
    except Exception as e:
        print(f"❌ ERROR converting WebM to Opus: {e}")
        import traceback
        traceback.print_exc()
        print(f"   ⚠️ Falling back to original WebM format...")
        # Fall back to original if conversion fails
        return base64_webm, None


async def upload_base64_to_firebase_storage(base64_data: str, file_name: str, file_type: str = "audio/webm") -> str:
    """
    Uploads base64 media to Firebase Storage and returns a public download URL.
    Firebase URLs are on Google's CDN and accessible by external services like MontyMobile.

    Args:
        base64_data: The base64-encoded file data
        file_name: Name for the file (e.g., "voice_message_123.ogg")
        file_type: MIME type of the file (default: "audio/webm")

    Returns:
        The Firebase Storage download URL, or local serve URL as fallback
    """
    try:
        import base64
        import uuid
        from urllib.parse import quote

        # Decode base64 to bytes
        file_bytes = base64.b64decode(base64_data)

        # Generate a unique filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        unique_filename = f"{timestamp}_{unique_id}_{file_name}"

        # Save locally as backup
        static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "audio")
        os.makedirs(static_dir, exist_ok=True)
        local_path = os.path.join(static_dir, unique_filename)
        with open(local_path, 'wb') as f:
            f.write(file_bytes)

        # Upload to Firebase Storage with a download token for public access
        try:
            from firebase_admin import storage as fb_storage
            bucket = fb_storage.bucket()
            storage_path = unique_filename
            blob = bucket.blob(storage_path)

            # Set download token for public URL access
            download_token = str(uuid.uuid4())
            blob.metadata = {"firebaseStorageDownloadTokens": download_token}
            blob.upload_from_string(file_bytes, content_type=file_type)

            # Build Firebase Storage download URL (publicly accessible with token)
            encoded_path = quote(storage_path, safe='')
            firebase_url = f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}/o/{encoded_path}?alt=media&token={download_token}"

            print(f"✅ Uploaded to Firebase Storage: {storage_path}")
            print(f"   Firebase URL: {firebase_url}")
            return firebase_url

        except Exception as e:
            print(f"⚠️ Firebase Storage upload failed: {e}")
            import traceback
            traceback.print_exc()

            # Fallback to local serve URL
            from services.media_service import build_public_media_url

            serve_url = build_public_media_url(unique_filename)
            if serve_url.startswith("/"):
                bot_domain = os.getenv("BOT_PUBLIC_DOMAIN", "linasaibot.com")
                serve_url = f"https://{bot_domain}{serve_url}"
            print(f"   Falling back to local serve URL: {serve_url}")
            return serve_url

    except Exception as e:
        print(f"❌ ERROR saving media file: {e}")
        import traceback
        traceback.print_exc()
        return None


async def update_dashboard_metric_in_firestore(user_id: str, metric_name: str, increment_by: int = 1):
    """
    Updates a specific dashboard metric in Firestore.
    Metrics are stored under a 'summary' document for each user.
    """
    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Skipping metric update.")
        return

    # Correct path: artifacts (collection) -> {appId} (document) -> users (collection) -> {userId} (document) -> dashboardMetrics (collection) -> summary (document)
    app_id_for_firestore = "linas-ai-bot-backend" 
    metrics_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_METRICS_COLLECTION).document('summary')

    try:
        # Get the current metrics document
        doc_snap = metrics_doc_ref.get() # Firebase Admin SDK get() is synchronous

        if doc_snap.exists:
            current_metrics = doc_snap.to_dict()
            current_value = current_metrics.get(metric_name, 0)
            metrics_doc_ref.update({metric_name: current_value + increment_by})
            print(f"✅ Updated metric '{metric_name}' for user {user_id} by {increment_by}. New value: {current_value + increment_by}")
        else:
            # If document doesn't exist, create it with the initial value
            metrics_doc_ref.set({metric_name: increment_by})
            print(f"✅ Created metric '{metric_name}' for user {user_id} with initial value {increment_by}.")

    except Exception as e:
        print(f"❌ ERROR updating dashboard metric '{metric_name}' in Firestore for user {user_id}: {e}")
        import traceback
        traceback.print_exc()

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

    def add(x: str):
        if x and x not in out:
            out.append(x)

    def add_alt_phone(c: str):
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
    conversation_id: str, user_id: str, request_user_id: str = None
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
    request_user_id: str = None,
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
                print(f"⚠️ update_conversation_on_all_existing_paths failed users/{vid}/conversations/{conversation_id}: {ex}")
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


def _clear_takeover_flags_for_user(resolved_user_id: str, raw_user_id: str, canonical_user_id: str):
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
    operator_id: str = None,
    operator_name: str = None,
    request_user_id: str = None,
    force_waiting_queue: bool = False,
):
    """
    Sets the human takeover status for a specific conversation in Firestore.
    This will control the AI's response for that chat.

    Args:
        user_id: The user's ID (room_id for Qiscus)
        conversation_id: The conversation document ID
        status: True to activate human takeover, False to release
        operator_id: Optional operator ID who is taking over
        operator_name: Optional operator name for display to customer
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
        raise ValueError(
            f"Conversation not found (conv={conversation_id}, searched {len(variants)} user id variants)"
        )

    resolved_user_id = existing[0][0]

    try:
        update_data = {
            "human_takeover_active": status,
            "last_updated": utc_now()
        }

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
                print(f"🔄 Setting conversation status to 'human' for operator takeover")
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
            update_data["post_release_escalation_suppressed_until"] = utc_now() + datetime.timedelta(
                minutes=_cd_mins
            )
            # GPT context: only messages at/after this timestamp are sent to the AI (fresh session after operator)
            update_data["ai_context_reset_at"] = utc_now()
            print(f"🔄 Setting conversation status to 'active' for bot release")

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
    window_hours: int = None,
    alternate_user_id: str = None,
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
        print(
            f"ℹ️ GPT context: in-memory transcript ({len(use)} msgs) > Firestore ({len(fs)}); using in-memory."
        )
        return openai_safe
    return fs


async def get_conversation_history_from_firestore(
    user_id: str,
    conversation_id: str,
    max_messages: int = 0,
    window_hours: int = None,
    alternate_user_id: str = None,
) -> list:
    """
    Fetches conversation history from Firestore for a specific conversation.
    Returns a list of messages in OpenAI format: [{"role": "user"/"assistant", "content": "text"}]
    Tries user_id first, then alternate_user_id (e.g. canonical), since save uses canonical_user_id.

    Args:
        user_id: The user's ID (room_id for Qiscus / raw WhatsApp id)
        conversation_id: The conversation document ID
        max_messages: Optional max number of messages after time filtering (0 = no hard cap)
        window_hours: Optional lookback window in hours (None = use config.CONTEXT_WINDOW_HOURS)
        alternate_user_id: Optional alternate user id (e.g. canonical) to try if user_id doc not found

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
        conv_doc_ref = users_coll.document(uid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
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
        messages = conversation_data.get('messages', [])

        # Time-based memory window: include only recent messages.
        effective_window_hours = (
            window_hours
            if window_hours is not None
            else int(getattr(config, "CONTEXT_WINDOW_HOURS", 12) or 12)
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
                    fallback=datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc),
                )
                if msg_ts >= cutoff:
                    filtered_messages.append(msg)

        # Optional hard cap after time filtering.
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
                _epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
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
            original_role = msg.get('role', 'user')

            # Map roles to OpenAI-compatible roles
            if original_role == 'ai':
                role = 'assistant'
            elif original_role == 'operator':
                # Treat operator messages as assistant (human staff responding)
                role = 'assistant'
            elif original_role in ['user', 'assistant', 'system', 'function', 'tool']:
                role = original_role
            else:
                # Skip unknown roles to prevent API errors
                print(f"⚠️ Skipping message with unknown role: {original_role}")
                continue

            content = msg.get('text', '')
            meta = msg.get('metadata', {}) or {}
            src = meta.get('source', '')
            if src == 'smart_message':
                content = f"[Clinic notification we sent to user]\n{content}"
            elif src == 'qa_database':
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


async def get_conversation_last_ai_response_at(user_id: str, conversation_id: str, alternate_user_id: str = None):
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
        conv_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
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


async def get_last_bot_message_from_conversation(user_id: str, conversation_id: str, alternate_user_id: str = None):
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
        conv_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
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
    conversation_id: Optional[str],
    alternate_user_id: str = None,
    within_hours: Optional[float] = None,
) -> Optional[dict]:
    """
    Last outbound message for GPT operational context. If the smart message was saved on another
    Firestore thread (identity/query mismatch), still surface it when it is newer than the current
    thread's last bot message. When conversation_id is missing, still returns a recent smart_message
    if any (e.g. new inbound right after restart before conv is resolved).
    """
    effective_within_hours = (
        float(within_hours)
        if within_hours is not None
        else float(getattr(config, "CONTEXT_WINDOW_HOURS", 12) or 12)
    )
    canonical = (alternate_user_id or "").strip() or user_id
    smart = await _latest_smart_ai_across_conversations(
        canonical, within_hours=effective_within_hours
    )
    if not conversation_id:
        return smart
    cur = await get_last_bot_message_from_conversation(
        user_id, conversation_id, alternate_user_id
    )

    def _ts(m: Optional[dict]):
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
        return smart
    if cur and not smart:
        return cur
    if not cur and not smart:
        return None
    if st and ct:
        return smart if st > ct else cur
    if st and not ct:
        return smart
    return cur


async def save_user_name_to_firestore(user_id: str, name: str):
    """
    Saves/updates a user's name in Firestore.

    Args:
        user_id: The user's ID (room_id for Qiscus or phone for others)
        name: The user's name to save
    """
    # Check if we're in testing mode - skip Firebase saving for tests
    if hasattr(config, 'TESTING_MODE') and config.TESTING_MODE:
        print(f"🧪 TESTING MODE: Skipping Firebase name save for user {user_id}")
        return

    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Skipping user name save.")
        return

    app_id_for_firestore = "linas-ai-bot-backend"
    user_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id)

    try:
        user_doc = user_doc_ref.get()
        if user_doc.exists:
            # Update existing user document with name
            user_doc_ref.update({
                "name": name,
                "last_activity": datetime.datetime.now()
            })
            print(f"✅ Updated user name in Firestore for {user_id}: {name}")
        else:
            # Create new user document with name
            user_doc_ref.set({
                "user_id": user_id,
                "name": name,
                "created_at": datetime.datetime.now(),
                "last_activity": datetime.datetime.now()
            })
            print(f"✅ Created user document in Firestore for {user_id} with name: {name}")
    except Exception as e:
        print(f"❌ ERROR saving user name to Firestore for {user_id}: {e}")
        import traceback
        traceback.print_exc()


async def get_user_state_from_firestore(user_id: str) -> dict:
    """
    Retrieves user state (gender, greeting_stage, name, phone) from Firestore.
    This is used to restore user state after server restart.

    Args:
        user_id: The user's ID (room_id for Qiscus)

    Returns:
        Dict with user state: {gender, greeting_stage, name, phone_full, phone_clean}
        Returns empty dict if user not found or error occurs.
    """
    import asyncio

    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Cannot retrieve user state.")
        return {}

    app_id_for_firestore = "linas-ai-bot-backend"
    user_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id)

    try:
        # ✅ Use asyncio.to_thread to prevent blocking the event loop
        user_doc = await asyncio.to_thread(user_doc_ref.get)
        if not user_doc.exists:
            print(f"ℹ️ No user document found in Firestore for user_id: {user_id}")
            # Try to get from most recent conversation's customer_info
            conversations_ref = user_doc_ref.collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
            # ✅ Use asyncio.to_thread for the query
            conversations = await asyncio.to_thread(
                lambda: list(conversations_ref.order_by("last_updated", direction=firestore.Query.DESCENDING).limit(1).get())
            )

            for conv in conversations:
                conv_data = conv.to_dict()
                customer_info = conv_data.get('customer_info', {})
                if customer_info:
                    print(f"✅ Found user state in conversation customer_info: {customer_info}")
                    return {
                        "gender": customer_info.get("gender", ""),
                        "greeting_stage": customer_info.get("greeting_stage", 0),
                        "name": customer_info.get("name", ""),
                        "phone_full": customer_info.get("phone_full", ""),
                        "phone_clean": customer_info.get("phone_clean", "")
                    }
            return {}

        user_data = user_doc.to_dict()
        print(f"✅ Retrieved user state from Firestore for {user_id}: gender={user_data.get('gender')}, greeting_stage={user_data.get('greeting_stage')}")

        return {
            "gender": user_data.get("gender", ""),
            "greeting_stage": user_data.get("greeting_stage", 0),
            "name": user_data.get("name", ""),
            "phone_full": user_data.get("phone_full", ""),
            "phone_clean": user_data.get("phone_clean", "")
        }

    except Exception as e:
        print(f"❌ ERROR retrieving user state from Firestore for {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return {}


# IMPORTANT: To avoid circular dependency, send_whatsapp_message cannot be imported directly here.
# It should be passed as a function argument if needed.
# For notify_human_on_whatsapp, we will keep the current print statement and
# add a comment that a real WhatsApp send would happen via main.py's send_whatsapp_message
# or by directly calling it if main.py's send_whatsapp_message is available globally or passed.

# For now, let's allow notify_human_on_whatsapp to *call* send_whatsapp_message from main.py if imported
# We'll need to modify main.py to pass it globally or import it here if safe.
# Safest way for now: The notify_human_on_whatsapp will explicitly import send_whatsapp_message *inside* its function
# to avoid circular imports unless main.py explicitly puts it into a global scope (like a dict or App object).
# Let's assume for now that main.py's send_whatsapp_message will be available for call.

# To handle this, we'll need a way for utils to access main.send_whatsapp_message
# The most practical way without complex architectural changes is to pass it as an argument
# to functions that need to notify, or to make it a global/callable attribute of 'app' in main.py.
# For simplicity, for now, notify_human_on_whatsapp will just *print* the notification.
# The actual WhatsApp send needs to be done by the calling handler in text_handlers.py or directly from main.py.

# Initialize OpenAI client safely
try:
    if config.OPENAI_API_KEY:
        client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    else:
        client = None
        print("⚠️  WARNING: OPENAI_API_KEY not set - LLM features disabled")
except Exception as e:
    client = None
    print(f"⚠️  WARNING: Failed to initialize OpenAI client: {e}")


def detect_language(text: str) -> dict:
    """
    Simple language detection for system-generated messages only.
    GPT handles language detection for user conversations.
    This is only used for error messages, rate limits, etc.
    """
    if not text or not text.strip():
        return {"language": "en", "confidence": 0.0}

    text = text.strip()

    # Count Arabic characters
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    text_length = len(text.replace(' ', ''))

    arabic_ratio = arabic_chars / text_length if text_length > 0 else 0

    # Arabic detection (50%+ Arabic characters)
    if arabic_ratio >= 0.5:
        return {"language": "ar", "confidence": arabic_ratio}

    # Simple French detection for common greetings/words
    text_lower = text.lower()
    french_indicators = ['bonjour', 'merci', 'je ', 'vous', 'oui', 'non', 'comment']
    if any(word in text_lower for word in french_indicators):
        return {"language": "fr", "confidence": 0.7}

    # Default to English
    return {"language": "en", "confidence": 0.5}



def notify_human_on_whatsapp(user_name, user_gender, message_content, type_of_notification="عام"):
    """
    Logs a notification and (in a full WhatsApp integration) would send a WhatsApp message to admin/staff.
    The actual sending via WhatsApp API must be done by the caller (e.g., in main.py or handlers)
    which has access to the send_whatsapp_message function.
    """
    current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time_str}] NOTIFY WHATSAPP: {type_of_notification} - From: {user_name} ({user_gender}) - Message: {message_content}")
    # To actually send a WhatsApp message here, main.py's send_whatsapp_message function
    # would need to be passed down or made globally accessible.
    # For now, it logs and the handler (e.g., text_handlers) will explicitly call send_whatsapp_message
    # to the WHATSAPP_TO number from config.
    # The existing calls in text_handlers.py and photo_handlers.py already handle the actual sending.
    print(f"Would send WhatsApp notification to {config.WHATSAPP_TO} (defined in .env).")


def count_tokens(text):
    if not text:
        return 0
    return len(text.split())

def save_for_training_conversation_log(user_message, bot_response):
    log_entry = {
        "question": user_message,
        "answer": bot_response,
        "language": detect_language(user_message)['language'],
        "timestamp": str(datetime.datetime.now())
    }
    try:
        os.makedirs('data', exist_ok=True)
        with open('data/conversation_log.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            f.flush()
    except Exception as e:
        print(f"❌ خطأ في حفظ سجل التدريب: {e}. قد تكون مشكلة أذونات أو مسار.")
        import traceback
        traceback.print_exc()

async def translate_qa_pair_with_gpt(question: str, answer: str, target_languages: list):
    """
    Translates a question/answer pair into target languages.
    Franco answer language will remain Arabic.
    """
    if not question or not answer:
        return []

    lang_map = {
        "ar": "Arabic",
        "en": "English",
        "fr": "French",
        "franco": "Franco Arabic"
    }

    translations = []

    # Standard translations (ar, en, fr)
    standard_target_languages = [lang for lang in target_languages if lang != "franco"]
    if standard_target_languages:
        standard_target_langs_str = ", ".join([f"'{l_code}' ({lang_map.get(l_code, l_code)})" for l_code in standard_target_languages])

        system_instruction_standard_translation = (
            "You are a highly accurate translator specializing in formulating questions and answers for a customer service bot. "
            f"Your task is to precisely translate the provided question and answer into the following languages: {standard_target_langs_str}. "
            "Maintain the original context and tone, suitable for a beauty/laser center customer service bot. "
            "The response MUST be in strict JSON format (a list of {{question, answer, language}} objects)."
            "**Required Example:**\n"
            "```json\n"
            "[\n"
            "  {{\"question\": \"What laser hair removal services do you offer?\", \"answer\": \"We offer advanced laser hair removal services using the latest technology to ensure optimal results. For a free consultation, you can book an appointment.\", \"language\": \"en\"}}\n"
            "]\n"
            "```\n"
            "Provide answers only within the specified JSON. Do not add any other text outside the JSON."
        )

        messages_standard = [
            {"role": "system", "content": system_instruction_standard_translation},
            {"role": "user", "content": f"Original Question: {question}\nOriginal Answer: {answer}"}
        ]

        try:
            response_standard = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages_standard,
                response_format={"type": "json_object"}
            )
            if not response_standard.choices:
                raise ValueError("GPT returned no choices")
            parsed_data_standard = json.loads(response_standard.choices[0].message.content.strip())
            if isinstance(parsed_data_standard, list):
                translations.extend(parsed_data_standard)
        except Exception as e:
            print(f"❌ ERROR in standard translation: {e}")
            pass


    # Translation to Franco Arabic (specific: Franco question, Arabic answer)
    if "franco" in target_languages:
        system_instruction_franco_translation = (
            "You are a highly accurate translator specializing in formulating questions and answers for a customer service bot. "
            "Your task is to precisely translate the original question into **Franco Arabic (franco)**, "
            "while keeping the **original answer as is in Arabic**. "
            "For Franco Arabic, use Latin characters to write Arabic words (e.g., 'kifak', 'shou'). Be creative in formulating colloquial Lebanese Franco. "
            "The response **MUST be in strict JSON format** (a single {{question, answer, language}} object)."
            "**Required Example:**\n"
            "```json\n"
            "{{\"question\": \"Sho sa3at 3amal al markaz?\", \"answer\": \"ساعات عمل مركز لينا ليزر هي من 10 صباحاً لـ 6 مساءً يومياً ما عدا الأحد.\", \"language\": \"franco\"}}\n"
            "```\n"
            "Return only the JSON. Do not add any other text outside the JSON."
        )
        messages_franco = [
            {"role": "system", "content": system_instruction_franco_translation},
            {"role": "user", "content": f"Original Question: {question}\nOriginal Answer (Arabic): {answer}"}
        ]
        try:
            response_franco = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages_franco,
                response_format={"type": "json_object"}
            )
            if not response_franco.choices:
                raise ValueError("GPT returned no choices")
            parsed_data_franco = json.loads(response_franco.choices[0].message.content.strip())
            if isinstance(parsed_data_franco, dict) and 'question' in parsed_data_franco and 'answer' in parsed_data_franco and 'language' in parsed_data_franco:
                translations.append(parsed_data_franco)
        except Exception as e:
            print(f"❌ ERROR in franco translation: {e}")
            pass

    return translations

# NEW FUNCTION: Define API Tools in OpenAI Function Calling format
def get_openai_tools_schema():
    """
    Returns the list of tools available to the OpenAI model in its required schema format.
    These definitions are based on LinasLaser AI Agent API Documentation.pdf.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "update_customer_profile",
                "description": (
                    "Update the saved profile for the current WhatsApp user when they explicitly ask to correct/change "
                    "their name or gender, or they say the bot is addressing them with the wrong gender/name. "
                    "Use this before replying to confirmations like 'my name is X now', 'change my name to X', "
                    "'I am female not male', 'ana bent mesh shab', or Arabic/franco equivalents. "
                    "Do not call this for weak inference; only when the user clearly provides the new value."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "new_name": {
                            "type": "string",
                            "description": "The corrected customer display name exactly as the user wants it saved. Omit if not changing name.",
                        },
                        "new_gender": {
                            "type": "string",
                            "enum": ["male", "female"],
                            "description": "Corrected gender in normalized backend format. Omit if not changing gender.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Short reason from the user's message, e.g. 'user requested gender correction'.",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_booking_intent",
                "description": (
                    "DEFAULT and REQUIRED path for every NEW booking: send structured extraction from the conversation. "
                    "The bot validates every field, resolves names to IDs using live CRM lists, enforces clinic slot rules, "
                    "then calls the CRM create endpoint only if validation passes. "
                    "Do NOT tell the user the appointment is booked unless this tool returns success with booking_flow_state=booked. "
                    "Do NOT use create_appointment for normal new bookings—use this tool first. "
                    "Leave IDs null when unsure; use get_services/get_branches/get_machines/get_body_parts first if needed. "
                    "Only Laser Hair Removal Men/Women (service_id 1/12) require a machine. For every other service, do NOT ask for machine and do NOT send machine_id. "
                    "If the user already supplied service, area, branch, date, time, and machine when required for hair removal in one message, extract all of them into this tool call; do not ask the same fields again. "
                    "DATETIME: Before execute_booking=true, resolve all relative NL into absolute values (Asia/Beirut). "
                    "IDs: By default the server does NOT convert service_name/branch_name/machine_name/body text to ids — "
                    "you MUST call get_services, get_branches, get_machines, get_body_parts and send service_id, branch_id, "
                    "machine_id (when required), body_part_ids, plus date/time/timezone. "
                    "Do not send name-only payloads with execute_booking=true. "
                    "raw_user_* and calendar_day_intent are optional trace fields only. "
                    "Legacy name resolution on the server exists only if the deployment sets LINASLASER_BOOKING_BACKEND_RESOLVES_NAMES=true. "
                    "For reschedule use update_appointment_date, not this tool."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intent": {
                            "type": "string",
                            "enum": ["create_appointment"],
                            "description": "Must be create_appointment for a new booking.",
                        },
                        "phone": {
                            "type": "string",
                            "description": "Customer phone without country code when possible; omit if same as runtime context.",
                        },
                        "service_name": {"type": "string", "description": "Human-readable service from user."},
                        "service_id": {"type": "integer", "description": "Only if already verified from get_services."},
                        "body_part": {
                            "type": "string",
                            "description": "Human-readable area hint from the user. Preserve it even when body_part_ids are available; never ask again when user already gave it.",
                        },
                        "body_part_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Non-empty list of CRM ids: call get_body_parts(service_id=…) and map every user-mentioned area to ids (multiple areas = multiple ids).",
                        },
                        "body_parts_with_sessions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "body_part_id": {"type": "integer"},
                                    "session_number": {
                                        "type": "integer",
                                        "description": "Per-area session index (1=first visit for that area, 2+=follow-up). Omit entirely for normal first bookings; server defaults all to 1.",
                                    },
                                },
                            },
                            "description": "Optional. When session numbers differ per area, pass one row per id (same ids as body_part_ids). Server sends BOC body_parts as {id, session_number} per official API doc.",
                        },
                        "machine_name": {"type": "string", "description": "Device name for Laser Hair Removal Men/Women only (Neo/Quadro/Candela/Trio). Do not use for other services."},
                        "machine_id": {"type": "integer", "description": "Only for service_id 1 or 12 after verified from get_machines. Omit for all other services."},
                        "branch_name": {"type": "string", "description": "Beirut or Antelias."},
                        "branch_id": {"type": "integer", "description": "Branch id from get_branches (commonly 1=Beirut, 3=Antelias; do not assume, use live list)."},
                        "gender": {"type": "string", "enum": ["male", "female"], "description": "Required for schedule rules if not already in session."},
                        "customer_name": {
                            "type": "string",
                            "description": "Full name in Latin for new CRM customers when file does not exist.",
                        },
                        "raw_user_date_text": {
                            "type": "string",
                            "description": "Optional: original user wording for logs (e.g. tomorrow). Not used as execution source if date+time are set.",
                        },
                        "raw_user_time_text": {
                            "type": "string",
                            "description": "Optional: original user time phrase for logs. Not execution source if time/date are resolved.",
                        },
                        "normalized_date": {"type": "string", "description": "If resolved, e.g. YYYY-MM-DD."},
                        "normalized_time": {"type": "string", "description": "If resolved, e.g. 15:00 or 3 PM phrasing already converted."},
                        "time": {
                            "type": "string",
                            "description": "Resolved clock time for execution when date is YYYY-MM-DD only, e.g. 09:00 or 17:30 (24h preferred).",
                        },
                        "timezone": {
                            "type": "string",
                            "description": "Execution timezone; use Asia/Beirut unless the deployment specifies otherwise.",
                        },
                        "calendar_day_intent": {
                            "type": "string",
                            "enum": ["today", "tomorrow"],
                            "description": "Optional hint for debugging; do not rely on this alone for execution—send resolved date+time.",
                        },
                        "date_components": {
                            "type": "object",
                            "description": "Concrete civil datetime after resolving vague weekday phrases.",
                            "properties": {
                                "year": {"type": "integer"},
                                "month": {"type": "integer"},
                                "day": {"type": "integer"},
                                "hour": {"type": "integer"},
                                "minute": {"type": "integer"},
                            },
                        },
                        "date": {
                            "type": "string",
                            "description": "Execution date or full datetime: YYYY-MM-DD, or YYYY-MM-DD HH:MM:SS, or ISO-like string. "
                            "Must be absolute (no 'tomorrow' as the only value). Combine with time when passing date-only.",
                        },
                        "missing_fields": {"type": "array", "items": {"type": "string"}},
                        "ambiguities": {"type": "array", "items": {"type": "string"}},
                        "needs_clarification": {"type": "boolean"},
                        "confidence_notes": {"type": "array", "items": {"type": "string"}},
                        "execute_booking": {
                            "type": "boolean",
                            "description": "Default true: after validation, call CRM create. Set false to dry-run only.",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_appointment",
                "description": (
                    "INTERNAL / LEGACY ONLY — do not call for normal new bookings. "
                    "Always use submit_booking_intent first; the server may still accept this tool for backward compatibility "
                    "but it runs the same CRM create step and returns the same structured success or validation-style failure "
                    "as submit_booking_intent (including when the calendar rejects the slot after local rules pass). "
                    "Requires phone, service_id, branch_id, date/time, and body_part_ids. "
                    "Only laser hair removal (1/12) uses customer-chosen device (get_machines: Neo/Quadro/Candela/Trio). "
                    "For tattoo/CO2/whitening/hydrofacial/HIFU/etc. omit machine_id entirely. "
                    "NEVER use for reschedule when a paused appointment exists—use update_appointment_date."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Client's phone number, e.g., '71 123 456'."},
                        "service_id": {"type": "integer", "description": "Service ID: 1=Hair Men, 12=Hair Women, 2/11=CO2, 13=Tattoo, 4/5/14=Whitening. For female hair removal use 12, not 3."},
                        "machine_id": {"type": "integer", "description": "Only for hair removal service_id 1/12. Omit for tattoo/CO2/whitening/hydrofacial/HIFU/etc."},
                        "branch_id": {"type": "integer", "description": "Branch id from get_branches (commonly 1=Beirut, 3=Antelias; do not assume)."},
                        "calendar_day_intent": {
                            "type": "string",
                            "enum": ["today", "tomorrow"],
                            "description": "REQUIRED when the user spoke in relative day terms (اليوم، el yom، lyom، بكرا، bokra، tomorrow، etc.): set 'today' or 'tomorrow' exactly as you understood their intent. The server uses this with the clinic clock to lock the calendar day even if the ISO date in 'date' is wrong. Omit only when the user gave an explicit calendar date (e.g. 21/03/2026 or 'next Saturday' resolved by you to a specific day).",
                        },
                        "date_components": {
                            "type": "object",
                            "description": "Optional but STRONGLY PREFERRED when the user used vague weekday phrases (الخميس الجاي، الجمعة الجاي، next Thursday…) or contradictory wording: after resolving to exactly ONE civil date using CALENDAR ANCHOR, pass year, month, day, hour (minute optional, default 0). Server builds API time from this first. If the user mentioned two different days, ask one clarification instead of guessing.",
                            "properties": {
                                "year": {"type": "integer", "description": "Gregorian year, e.g. 2026"},
                                "month": {"type": "integer", "description": "1-12"},
                                "day": {"type": "integer", "description": "1-31"},
                                "hour": {"type": "integer", "description": "0-23 (24h; 13 = 1 PM)"},
                                "minute": {"type": "integer", "description": "0-59; omit or 0 if not specified"},
                            },
                        },
                        # This is derived from the API Documentation PDF
                        "date": {"type": "string", "format": "date-time", "description": "Full appointment date and time in 'YYYY-MM-DD HH:MM:SS' format (e.g., '2025-07-28 19:30:00'). Must match date_components when provided. Convert natural language using CURRENT DATE AND TIME / CALENDAR ANCHOR. For 'today'/'tomorrow' set calendar_day_intent. For next-Thursday-style phrases, prefer filling date_components."},
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."},
                        "body_part_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 1,
                            "description": "**REQUIRED for all services** (hair, tattoo, CO2, whitening, etc.). Non-empty array of numeric body_part_id values from get_body_parts for the chosen service_id.",
                        },
                        "body_parts_with_sessions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "body_part_id": {"type": "integer"},
                                    "session_number": {"type": "integer", "description": "Use 1 for new/first-time bookings unless the user or CRM context says otherwise (2+ = follow-up session for that area)."},
                                },
                            },
                            "description": "Optional; session numbers per area. Default create sends body_parts [{id, session_number}]. LINASLASER_APPOINTMENT_BODY_PART_IDS_ONLY=1 forces body_part_ids only when all sessions are 1.",
                        },
                    },
                    "required": ["phone", "service_id", "branch_id", "date", "body_part_ids"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_appointment_date",
                "description": (
                    "Updates the date/time of an existing appointment on the calendar. Use for reschedule/postpone/change to a NEW slot (Arabic «تأجيل الموعد»). "
                    "Same tool to put a PAUSED row onto a new datetime once the user chose the slot—this also covers phrasing like «يرجع يجي عالموعد», «كمّل الموعد», or 'resume the paused appointment'. Do NOT call pause_appointment for that. "
                    "If that row was PAUSED and the customer is continuing with it, do NOT leave it paused after this update. "
                    "You MUST pass the **exact appointment_id** the user selected (from check_next_appointment / customer_appointments JSON), plus structured **date**. "
                    "If multiple rows: first show each row to the user with appointment_id + service + machine + areas + price (if in JSON), ask them for the id (or line number), then call this tool. "
                    "Do NOT use pause_appointment to move to another day. "
                    "When the response is success=true, the Agent API accepted the change. The payload may include resume_appointment: after date update the server may POST a resume endpoint so Paused→Available—if resume_appointment.success is true, tell the user the slot is active at the new time; if resume failed or was skipped, datetime still changed but status may stay Paused until staff or API fixes it. Read hint_for_model."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "integer",
                            "description": "Numeric appointment id from CRM JSON (appointment_id / id)—the row the user chose to move or re-activate from pause.",
                        },
                        "phone": {"type": "string", "description": "Client's phone number (without country code), e.g., '71 123 456'."},
                        "calendar_day_intent": {
                            "type": "string",
                            "enum": ["today", "tomorrow"],
                            "description": "When the user asked to move the appointment to 'today' or 'tomorrow' (اليوم، el yom، بكرا، etc.), set this so the server locks the correct day. Omit if they gave only an explicit calendar date.",
                        },
                        "date_components": {
                            "type": "object",
                            "description": "Same as create_appointment: optional structured year/month/day/hour/(minute) after you resolved the new slot; preferred for weekday-relative wording.",
                            "properties": {
                                "year": {"type": "integer"},
                                "month": {"type": "integer"},
                                "day": {"type": "integer"},
                                "hour": {"type": "integer"},
                                "minute": {"type": "integer"},
                            },
                        },
                        "date": {"type": "string", "format": "date-time", "description": "New appointment date and time in 'YYYY-MM-DD HH:MM:SS' format (e.g., '2025-11-15 16:00:00'). Must match date_components when provided. Convert natural language; if relative day, set calendar_day_intent too."},
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."}
                    },
                    "required": ["appointment_id", "phone", "date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "resume_appointment",
                "description": (
                    "Re-activates a PAUSED appointment without changing its date/time. "
                    "Use this when the customer says things like «رجّع الموعد», «رجع خليه available», "
                    "«please rj3 hotle el mw3ad», or wants the paused row to become active again with the same slot. "
                    "You MUST pass the exact paused appointment_id the user selected from CRM JSON. "
                    "If multiple paused rows exist, list them first and ask which appointment_id/line they mean. "
                    "Do not use this tool for a new date/time; for that use update_appointment_date."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "integer",
                            "description": "Paused appointment id to restore to Available.",
                        },
                        "phone": {
                            "type": "string",
                            "description": "Client phone number (local format accepted).",
                        },
                        "user_code": {
                            "type": "string",
                            "description": "Optional compatibility field; ignored by current backend implementation.",
                        }
                    },
                    "required": ["appointment_id", "phone"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_paused_appointment",
                "description": (
                    "Advanced paused-appointment edit. Use when the user wants to modify a paused row details beyond date only "
                    "(body parts, session_number per part, machine, and/or explicit status to Available). "
                    "If the paused customer is continuing with this appointment, you MUST explicitly set `status` to `Available` in the same tool call so the row does not stay paused after the edit. "
                    "Pass appointment_id selected by the user. This executes one CRM update payload for that paused row. "
                    "After **success**, tell the user the **new session/total price** from the API response (or fetch via get_appointment_details). "
                    "If a **final agreed price** was already set with the customer for this appointment_id, call **sync_appointment_agreed_price** in the same turn (or immediately after) with that agreed_price so the system stays aligned."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {"type": "integer", "description": "Paused appointment id to edit."},
                        "phone": {"type": "string", "description": "Client phone (local format accepted)."},
                        "date": {"type": "string", "format": "date-time", "description": "Optional new datetime YYYY-MM-DD HH:MM:SS."},
                        "machine_id": {"type": "integer", "description": "Optional machine id (service-dependent)."},
                        "body_part_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Optional replacement body-part ids list."
                        },
                        "body_parts_with_sessions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "body_part_id": {"type": "integer"},
                                    "session_number": {"type": "integer", "description": ">=1"}
                                }
                            },
                            "description": "Optional per-body-part sessions. Preferred when session numbers matter."
                        },
                        "status": {
                            "type": "string",
                            "description": "Optional target status (e.g. Available). If omitted, server may default to Available for paused edits."
                        },
                        "user_code": {"type": "string", "description": "Optional user_code."}
                    },
                    "required": ["appointment_id", "phone"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "edit_appointment",
                "description": (
                    "FULL update of an existing appointment per BOC API (POST /appointments/edit): "
                    "service, machine, branch, date, body_parts with per-area session_number, discounts. "
                    "Use when the user changes several fields at once or replaces body areas/sessions. "
                    "For **date-only** reschedule prefer update_appointment_date. "
                    "If the edited row is PAUSED and the customer is continuing with it, do NOT use this tool alone: also call `resume_appointment` in the same turn so the appointment becomes Available again. "
                    "Either phone OR user_code required. Do not send root session_number together with body_parts unless the API requires it. "
                    "After **success**, always communicate the **new session/total price** to the user (from response JSON or get_appointment_details). "
                    "If you had an **agreed final price** with the customer for this appointment_id, call **sync_appointment_agreed_price** with the same agreed_price so CRM discount matches after body/machine changes."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {"type": "integer", "description": "CRM appointment id to edit."},
                        "phone": {"type": "string", "description": "Customer phone (local format); required if user_code omitted."},
                        "user_code": {"type": "string", "description": "Customer code; required if phone omitted."},
                        "service_id": {"type": "integer", "description": "Optional new service id."},
                        "machine_id": {"type": "integer", "description": "Optional new machine id."},
                        "branch_id": {"type": "integer", "description": "Optional new branch id."},
                        "date": {"type": "string", "description": "Optional new datetime YYYY-MM-DD HH:MM:SS (must be future)."},
                        "body_part_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Optional; if body_parts_with_sessions omitted, builds body_parts with same session_number.",
                        },
                        "body_parts_with_sessions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "body_part_id": {"type": "integer"},
                                    "id": {"type": "integer", "description": "Same as body_part_id if you prefer."},
                                    "session_number": {"type": "integer"},
                                },
                            },
                            "description": "Replace appointment body areas; API uses body_parts[].id + session_number.",
                        },
                        "session_number": {
                            "type": "integer",
                            "description": "Use only when NOT sending body_parts; applies with body_part_ids fallback.",
                        },
                        "discount_percentage": {"type": "number"},
                        "discount_amount": {"type": "number"},
                        "total_cost_after_discount": {"type": "number"},
                        "hidden": {"type": "boolean"},
                    },
                    "required": ["appointment_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_branches",
                "description": "Retrieves a list of all branches associated with the clinic.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_services",
                "description": "Retrieves a list of all services offered by the clinic.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_machines",
                "description": "Lists machines in the clinic. Call when booking laser hair removal (service 1 or 12) to pick the device the customer agreed to (Neo, Quadro, Candela, Trio). For tattoo, CO2, or whitening you may still call once to get a valid machine_id for the API, but do not ask the customer to choose a device for those services.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_service_data",
                "description": (
                    "GET /service/data (Appointment API): returns pricing and body_parts options for a service_id, "
                    "optional machine_id. Recommended before create to show price/options to the user (per BOC doc flow)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "integer", "description": "Service to quote (same as booking)."},
                        "machine_id": {"type": "integer", "description": "Optional filter when machine is known."},
                    },
                    "required": ["service_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_body_parts",
                "description": (
                    "Returns the official CRM list of bookable body areas (id + name) for a service, optionally filtered by machine. "
                    "REQUIRED before submit_booking_intent whenever the user names one or more areas (Arabic/English/franco) "
                    "or you need numeric body_part_ids. Always pass the same service_id you are booking "
                    "(1 = laser hair removal men, 12 = women, 13 = tattoo, etc.). "
                    "When a machine is required/selected for this booking, pass machine_id too so the API can return the exact body-part list for that service+machine. "
                    "Match each user-mentioned area to rows in this response and pass every matching id in submit_booking_intent.body_part_ids "
                    "(multiple areas = multiple ids). Do not guess ids from memory or pricing text; use this tool. "
                    "If this tool returns success=false, read hint_for_model if present: do NOT ask the user for 'CRM/system' area names when "
                    "they already described the body location; use submit_booking_intent.body_part with their wording instead when possible."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {
                            "type": "integer",
                            "description": (
                                "Same service as the booking conversation, e.g. 1 or 12 for laser hair removal "
                                "(use 1 for male / شاب، 12 for female / صبية). Required for correct area ids."
                            ),
                        },
                        "machine_id": {
                            "type": "integer",
                            "description": "Optional but recommended when machine is known/required for the booking; filters body parts by service+machine."
                        },
                    },
                    "required": ["service_id"],
                },
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_clinic_hours",
                "description": "Returns the clinic's working hours for each day of the week.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_appointment_reminders",
                "description": "Triggers the sending of appointment reminders to clients.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date", "description": "Specific date for reminders (YYYY-MM-DD, optional)."},
                        "phone": {"type": "string", "description": "Client's phone number (required if user_code not provided)."},
                        "user_code": {"type": "string", "description": "Client's unique user code (required if phone is not provided)."}
                    },
                    "required": [] # API docs state "required if other not provided"
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_next_appointment",
                "description": (
                    "Returns the client's next appointment and (when available) customer_appointments: all rows from the system. "
                    "For user-facing replies: **one line per row**, each starting with the numeric **appointment_id** from JSON (same as id). "
                    "Include date, time, service, branch, machine/device, body areas/parts, and price/total **only if** those fields exist in the JSON—never invent prices. "
                    "When several rows exist and the user must choose (reschedule, resume from pause, etc.), ask them to send the **appointment_id** they want "
                    "(or the line number 1/2/3 matching your list). Use tool JSON to map their answer to the correct id for update_appointment_date. "
                    "If status is paused/postponed, update that existing row—do not create a new appointment."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Client's phone number."},
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."}
                    },
                    "required": ["phone"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_sessions_count_by_phone",
                "description": "Returns the number of sessions a client has attended, based on their phone number or user code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Client's phone number (required if user_code is not provided)."},
                        "user_code": {"type": "string", "description": "Client's unique user code (required if phone is not provided)."},
                        "service_ids": {"type": "array", "items": {"type": "integer"}, "description": "Filter sessions by specific service IDs (e.g., service_ids[]=1&service_ids[]=2)."}
                    },
                    "required": [] # API says phone or user_code required
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "move_client_branch",
                "description": "Moves a client's future appointments to a different branch. new_date is optional: include only when the Agent API / ops require rescheduling moved rows to a specific day.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Client's phone number."},
                        "from_branch_id": {"type": "integer", "description": "ID of the current branch."},
                        "to_branch_id": {"type": "integer", "description": "ID of the new branch."},
                        "new_date": {"type": "string", "format": "date", "description": "Optional. YYYY-MM-DD when a new date must be sent with the move; omit for branch-only move if allowed by API."},
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."},
                        "response_confirm": {"type": "string", "description": "Confirmation of the move, default 'yes'."}
                    },
                    "required": ["phone", "from_branch_id", "to_branch_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_appointment_payment",
                "description": "Checks the payment status of a client's appointments.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Client's phone number."},
                        "user_code": {"type": "string", "description": "Client's unique user code (optional)."}
                    },
                    "required": ["phone"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_missed_appointments",
                "description": "Returns a list of missed appointments for the clinic.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date", "description": "Filter missed appointments by a specific date (YYYY-MM-DD, optional)."}
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_customer_by_phone", # NEW API Function
                "description": "Retrieves customer details by phone number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Customer's phone number."}
                    },
                    "required": ["phone"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_customer_gender",
                "description": "Returns the gender of a customer based on the provided identifier.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Customer's phone number (required if user_code is not provided)."},
                        "user_code": {"type": "string", "description": "Customer's unique user code (required if phone is not provided)."}
                    },
                    "required": [] # API says phone or user_code is required
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "retrieve_relevant_knowledge",
                "description": "Retrieve relevant knowledge/price/style files for the user's question. Call this when you need more context to answer accurately (e.g. body areas, service details, pricing philosophy). The bot will send the user message to a selector AI, get selected files, and return their content. Use that content to formulate your reply.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_message": {"type": "string", "description": "The user's message or question to match against available files."}
                    },
                    "required": ["user_message"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_appointment_details",
                "description": "Retrieves detailed information about a specific appointment by appointment ID (customer, date, time, service, machine, branch, status, price, payment_status).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {"type": "integer", "description": "The ID of the appointment to retrieve."}
                    },
                    "required": ["appointment_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "sync_appointment_agreed_price",
                "description": (
                    "When you and the customer have **explicitly agreed** on a **final total price** for a specific appointment already in CRM "
                    "(new booking just created, existing row, or after any change)—call this so the backend can align the system price. "
                    "The server reads the current CRM total (or uses `system_total_known` if you pass it from the last booking response), "
                    "and if the CRM price is **higher** than the agreed amount, it POSTs `appointments/discount/add` with the difference. "
                    "**Important:** after **edit_appointment** / **update_paused_appointment** changes **body parts** or **machine**, CRM may show a **new** list total—call this again with the **same** agreed_price and **same** appointment_id to re-apply alignment. "
                    "Do not invent numbers: only use after the user clearly confirmed the price. "
                    "If agreed price is higher than CRM, the tool will not increase CRM price—explain honestly."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "integer",
                            "description": "CRM appointment id (from booking/create response, check_next_appointment, or get_appointment_details).",
                        },
                        "agreed_price": {
                            "type": "number",
                            "description": "Final total price you and the customer agreed on (same currency as CRM).",
                        },
                        "system_total_known": {
                            "type": "number",
                            "description": (
                                "Optional. Pass the CRM total from the **last** create/booking tool response if you have it, "
                                "to avoid an extra lookup. Omit to fetch current price from get_appointment_details."
                            ),
                        },
                    },
                    "required": ["appointment_id", "agreed_price"],
                },
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_clients_without_today",
                "description": "Returns active clients who do not have appointments on the given date. Useful for outreach or availability checks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date", "description": "Date to check (YYYY-MM-DD). Defaults to today if not provided."},
                        "branch_id": {"type": "integer", "description": "Filter by branch ID (optional)."}
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_customer_sessions",
                "description": "Returns sessions (appointments) for a customer by customer_id, including service, body area, session number, status, and notes. Use customer_id from get_customer_by_phone response.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "integer", "description": "Customer ID (from get_customer_by_phone data.id)."}
                    },
                    "required": ["customer_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "add_customer_note",
                "description": "Adds a note to the customer's record (e.g. follow-up request, preference, complaint).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Customer's phone number."},
                        "note": {"type": "string", "description": "Note content (max 1000 characters)."}
                    },
                    "required": ["phone", "note"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_all_customers",
                "description": "Returns a list of all customers. Can filter by creation date (date, from, to).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date", "description": "Customers created on this date (YYYY-MM-DD)."},
                        "from_date": {"type": "string", "format": "date", "description": "Customers created on or after this date (YYYY-MM-DD)."},
                        "to_date": {"type": "string", "format": "date", "description": "Customers created on or before this date (YYYY-MM-DD)."}
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_customer",
                "description": "Creates a new customer record within the clinic's database.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Full name of the customer."},
                        "phone": {"type": "string", "description": "Customer's phone number."},
                        "email": {"type": "string", "format": "email", "description": "Customer's email (optional)."},
                        "gender": {"type": "string", "enum": ["Male", "Female"], "description": "Customer's gender (must be 'Male' or 'Female')."}, # Updated enum
                        "branch_id": {"type": "integer", "description": "Preferred branch ID for the customer."}, # Made required
                        "date_of_birth": {"type": "string", "format": "date", "description": "Customer's date of birth (YYYY-MM-DD, optional)."}
                    },
                    "required": ["name", "phone", "gender", "branch_id"] # Updated required fields
                }
            }
        },
    ]
    return tools

def get_system_instruction(
    user_id,
    response_lang,
    qa_reference: str = "",
    include_price_list: bool = True,
    custom_knowledge_context: str = None,
    operational_context: str = None,
):
    """
    Generate system instruction for GPT.

    Args:
        user_id: User identifier
        response_lang: Response language code (ar, en, fr, franco)
        qa_reference: Kept for backward compatibility (currently not injected)
        include_price_list: Whether to include the price_list.txt content in prompt context
        custom_knowledge_context: When provided (dynamic retrieval), ADDITIVE to KB/Style - never replaces
        operational_context: Structured block with state, original_question, task (Plan §10)
    """
    _ = qa_reference  # compatibility placeholder
    user_gender_str = config.user_gender.get(user_id, "unknown")
    
    gender_instruction = ""
    if user_gender_str == "male":
        gender_instruction = "The user is male. You MUST use masculine forms exclusively in all your replies (e.g., 'Hello sir', 'How can I help you', 'I saw your question', 'tell us'). Adhere strictly to masculine phrasing in every sentence, verb, noun, and adjective. Do not mix forms."
    elif user_gender_str == "female":
        gender_instruction = "The user is female. You MUST use feminine forms exclusively in all your replies (e.g., 'Hello madam', 'How can I help you', 'I saw your question', 'tell us'). Adhere strictly to feminine phrasing in every sentence, verb, noun and adjective. Do not mix forms."
    else: # This means gender is "غير محدد" or "unknown"
        gender_instruction = """
        **GENDER DECISION POLICY (AI-PRIMARY):**
        User's gender is UNKNOWN.
        - You are the decision owner: decide from context whether gender is required now.
        - If gender is required for safe/personalized next step, use action "ask_gender".
        - If gender is not required for the current informational answer, answer directly.
        - When the user provides gender, use action "confirm_gender" and continue naturally.
        - Use neutral wording whenever gender is still unknown.
        """
    
    price_list_section = ""
    if include_price_list and config.PRICE_LIST:
        price_list_section = f"""
        **💰 PRICE LIST:** (Use this to answer pricing questions)
        {config.PRICE_LIST}
        """

    # KB + Style are ALWAYS the foundation. Selector content (custom_knowledge_context) builds on top.
    knowledge_section = f"""
        **🔴 STYLE GUIDE (MANDATORY - Foundation - FOLLOW EVERY STEP IN ORDER):**
        The following contains MANDATORY rules for how you communicate AND the exact step-by-step flow for each service. You MUST follow every step in order. Do NOT skip steps. Do NOT jump ahead to booking if a step requires waiting (e.g., waiting for a photo before giving pricing).

        {config.BOT_STYLE_GUIDE}

        **📘 CORE KNOWLEDGE BASE (Foundation):** (Use this to answer questions about services, devices, IDs, and matching rules)
        {config.CORE_KNOWLEDGE_BASE}

        {price_list_section}
        """
    if custom_knowledge_context:
        knowledge_section += f"""
        **📂 ADDITIONAL RELEVANT CONTEXT (Selector - use for this specific query):**
        {custom_knowledge_context}
        """

    operational_block = ""
    if operational_context:
        operational_block = f"""
        **📋 CONVERSATION STATE & TASK (Operational Context):**
        {operational_context}
        """

    # Keep token compatibility, but do not inject trained Q&A reference rules into GPT prompt.
    qa_reference_block = ""

    prompt_template = getattr(config, "SYSTEM_PROMPT_TEMPLATE", "")
    if not isinstance(prompt_template, str):
        prompt_template = ""

    # Safety fallback: avoid silently sending an empty system prompt when template file is blank/missing.
    # This keeps knowledge/style/operational sections active and prevents fragile runtime behavior.
    if not prompt_template.strip():
        prompt_template = DEFAULT_SYSTEM_PROMPT_TEMPLATE

    rendered_prompt = prompt_template
    token_values = (
        (KNOWLEDGE_SECTION_TOKEN, knowledge_section),
        (OPERATIONAL_BLOCK_TOKEN, operational_block),
        (GENDER_INSTRUCTION_TOKEN, gender_instruction),
        (QA_REFERENCE_BLOCK_TOKEN, qa_reference_block),
    )

    # Robust behavior for custom templates:
    # if a required token is missing from SYSTEM_PROMPT_TEMPLATE, append that section
    # so dynamic selector content/guardrails are never silently dropped.
    missing_tokens = []
    missing_sections = []
    for token, value in token_values:
        section_text = value or ""
        if token in rendered_prompt:
            rendered_prompt = rendered_prompt.replace(token, section_text)
        elif section_text.strip():
            missing_tokens.append(token)
            missing_sections.append(section_text.strip())

    if missing_sections:
        print(
            "⚠️ SYSTEM_PROMPT_TEMPLATE missing placeholders: "
            + ", ".join(missing_tokens)
            + ". Appending sections to preserve runtime context."
        )
        rendered_prompt = rendered_prompt.rstrip() + "\n\n" + "\n\n".join(missing_sections)

    return rendered_prompt
