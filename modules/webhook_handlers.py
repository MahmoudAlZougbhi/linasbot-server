# -*- coding: utf-8 -*-
"""
Webhook handlers module: Message parsing and processing
Handles webhook reception, parsing, and routing messages to appropriate handlers.
"""

import asyncio
import hashlib
import json
import uuid
import re
import datetime
import io
import os
import time
from typing import Dict, Any, Optional

from google.cloud import firestore

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import httpx

from modules.core import app, whatsapp_api_client, dashboard_bot_responses
from modules.models import WebhookRequest
import config
from config import WHATSAPP_API_TOKEN
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory
from services.whatsapp_adapters.outbound_text_dedupe import normalize_text_body_for_dedupe
from utils.phone_utils import phone_match_key
from utils.utils import get_firestore_db, set_human_takeover_status, save_conversation_message_to_firestore
from services.api_integrations import log_report_event
from handlers.text_handlers import handle_message, start_command, _delayed_processing_tasks, _process_and_respond
from handlers.training_handlers import handle_training_input
from handlers.voice_handlers import handle_voice_message
from handlers.training_handlers import start_training_mode, exit_training_mode

# Webhook deduplication cache: {message_id: timestamp}
# Prevents processing the same webhook multiple times within a time window
_webhook_dedup_cache = {}
# Per-message_id lock so check+record is atomic (avoids two concurrent requests both passing memory dedupe when Firestore is down / fail-open).
_webhook_memory_dedup_locks: Dict[str, asyncio.Lock] = {}
WEBHOOK_DEDUP_WINDOW_SECONDS = 60  # Consider duplicate if received within 60 seconds (Qiscus can send duplicates up to 15+ seconds apart)

# Some providers deliver the same user text twice with different message ids; message_id dedupe misses that.
# MontyMobile / retries can arrive >5s apart — keep a generous window so we do not run GPT twice for one user tap.
WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS = 45.0
WEBHOOK_TEXT_BODYFP_MAX_CHARS = 4000
_webhook_bodyfp_cache: Dict[str, float] = {}
_webhook_bodyfp_locks: Dict[str, asyncio.Lock] = {}


def _webhook_text_body_fingerprint(parsed_message: Dict[str, Any]) -> str:
    """
    Stable key for short-window text dedupe (same logical sender + same body).
    Aligns phone with phone_match_key (+961 vs 961, room→phone) and text with outbound NFKC/ZW normalization
    so parallel workers and duplicate provider deliveries collapse to one fingerprint.
    """
    if (parsed_message.get("type") or "") != "text":
        return ""
    text = _extract_text_from_content(parsed_message.get("content"))
    text = normalize_text_body_for_dedupe(text)
    if not text:
        return ""
    text = text[:WEBHOOK_TEXT_BODYFP_MAX_CHARS]
    raw_sender = (parsed_message.get("phone_number") or parsed_message.get("user_id") or "").strip()
    sender_key = phone_match_key(raw_sender)
    if not sender_key:
        # Room / non-E.164 ids: still dedupe duplicate webhooks for the same provider id
        sid = (parsed_message.get("user_id") or raw_sender or "").strip()
        if not sid:
            return ""
        sender_key = "id_" + hashlib.sha256(sid.encode("utf-8", errors="replace")).hexdigest()[:24]
    basis = f"{sender_key}|{text}"
    return "bodyfp_" + hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()[:48]


async def _webhook_bodyfp_try_claim(fp: str, current_time: float) -> bool:
    if not fp:
        return True
    expired = [
        k
        for k, ts in _webhook_bodyfp_cache.items()
        if current_time - ts > WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS
    ]
    for k in expired:
        _webhook_bodyfp_cache.pop(k, None)
        _webhook_bodyfp_locks.pop(k, None)

    lock = _webhook_bodyfp_locks.setdefault(fp, asyncio.Lock())
    async with lock:
        if fp in _webhook_bodyfp_cache:
            return False
        _webhook_bodyfp_cache[fp] = current_time
        return True


async def _webhook_memory_try_claim(message_id: str, current_time: float) -> bool:
    """
    Return True if this request should proceed, False if duplicate within WEBHOOK_DEDUP_WINDOW_SECONDS.
    Atomic per message_id for same-process concurrent webhooks.
    """
    mid = (message_id or "").strip()
    if not mid:
        return True

    expired_keys = [
        k for k, v in _webhook_dedup_cache.items() if current_time - v > WEBHOOK_DEDUP_WINDOW_SECONDS
    ]
    for k in expired_keys:
        _webhook_dedup_cache.pop(k, None)
        _webhook_memory_dedup_locks.pop(k, None)

    lock = _webhook_memory_dedup_locks.setdefault(mid, asyncio.Lock())
    async with lock:
        if mid in _webhook_dedup_cache:
            return False
        _webhook_dedup_cache[mid] = current_time
        return True


def _synthetic_inbound_id_from_wa_message(msg: dict) -> str:
    """When WhatsApp message.id is missing, dedupe keys must not collapse to one value."""
    basis = json.dumps(msg, sort_keys=True, default=str)
    return "synth_" + hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()[:48]


async def _webhook_firestore_try_acquire(message_id: str) -> bool:
    """
    Return True if we should process this inbound WhatsApp message_id.
    Return False if another worker (or earlier request) already registered it (duplicate webhook).
    """
    mid = (message_id or "").strip()
    if not mid:
        return True
    db = get_firestore_db()
    if not db:
        return True
    doc_id = hashlib.sha256(mid.encode("utf-8")).hexdigest()
    ref = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("webhook_inbound_processed")
        .document(doc_id)
    )

    def _create():
        ref.create(
            {
                "created_at": firestore.SERVER_TIMESTAMP,
                "message_id_prefix": mid[:200],
            }
        )

    def _is_dup(exc: BaseException) -> bool:
        if type(exc).__name__ in ("AlreadyExists", "Conflict"):
            return True
        code = getattr(exc, "code", None)
        if code in (409, "ALREADY_EXISTS"):
            return True
        s = str(exc).lower()
        return "already exists" in s or "already_exists" in s

    try:
        await asyncio.to_thread(_create)
        return True
    except Exception as e:
        if _is_dup(e):
            return False
        print(f"⚠️ Webhook Firestore dedupe create failed (using memory fallback): {e}")
        return True


async def _webhook_bodyfp_firestore_try_acquire(body_fp: str, current_time: float) -> bool:
    """
    Multi-worker: same inbound text + sender within WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS (bucketed)
    should only enqueue one process_parsed_message, even when the provider sends different message_ids.
    """
    fp = (body_fp or "").strip()
    if not fp:
        return True
    db = get_firestore_db()
    if not db:
        return True
    slot = int(current_time // WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS)
    basis = f"{fp}\0bodyfp_slot{slot}"
    doc_id = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    ref = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("webhook_text_body_processed")
        .document(doc_id)
    )

    def _create():
        ref.create(
            {
                "created_at": firestore.SERVER_TIMESTAMP,
                "body_fingerprint_prefix": fp[:120],
                "time_slot": slot,
            }
        )

    def _is_dup(exc: BaseException) -> bool:
        if type(exc).__name__ in ("AlreadyExists", "Conflict"):
            return True
        code = getattr(exc, "code", None)
        if code in (409, "ALREADY_EXISTS"):
            return True
        s = str(exc).lower()
        return "already exists" in s or "already_exists" in s

    try:
        await asyncio.to_thread(_create)
        return True
    except Exception as e:
        if _is_dup(e):
            return False
        print(f"⚠️ Webhook body-fp Firestore dedupe create failed (fail-open): {e}")
        return True


# Second line of defense: same worker can queue two process_parsed_message tasks for the same message_id
# (e.g. webhook handler returns before Firestore create is visible). Serialize + skip duplicate in-process.
_process_parsed_mid_locks: Dict[str, asyncio.Lock] = {}
_process_parsed_mid_claims: Dict[str, float] = {}
_PROCESS_PARSED_MID_TTL_SECONDS = 120.0


async def _process_parsed_should_skip_duplicate(message_id: str) -> bool:
    """Return True if this message_id is already being or was recently processed (skip)."""
    mid = (message_id or "").strip()
    if not mid:
        return False
    now = time.time()
    expired = [
        k
        for k, ts in _process_parsed_mid_claims.items()
        if now - ts > _PROCESS_PARSED_MID_TTL_SECONDS
    ]
    for k in expired:
        _process_parsed_mid_claims.pop(k, None)
        _process_parsed_mid_locks.pop(k, None)

    lock = _process_parsed_mid_locks.setdefault(mid, asyncio.Lock())
    async with lock:
        if mid in _process_parsed_mid_claims:
            print(f"⚠️ skip duplicate process_parsed_message (in-process): {mid[:56]}...")
            return True
        _process_parsed_mid_claims[mid] = now
    return False


def _process_parsed_release_claim_on_error(message_id: str) -> None:
    mid = (message_id or "").strip()
    if not mid:
        return
    _process_parsed_mid_claims.pop(mid, None)
    _process_parsed_mid_locks.pop(mid, None)


async def await_whatsapp_delayed_processing(user_id: str) -> None:
    """
    handle_message() schedules combine+GPT in a Task and returns immediately. process_parsed_message
    is also run via ensure_future after the webhook returns 200 — if we do not await this task here,
    the background chain can end before the reply is sent (users see no AI response on WhatsApp).
    """
    if user_id not in _delayed_processing_tasks:
        return
    task = _delayed_processing_tasks[user_id]
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        print(f"⚠️ [webhook] Delayed processing cancelled for user_id={user_id}")
    except Exception as e:
        print(f"❌ [webhook] Delayed processing failed for user_id={user_id}: {e}")
    finally:
        _delayed_processing_tasks.pop(user_id, None)

# Debug: last webhook received/parsed (for /api/debug/webhook-status)
_last_webhook_received_at = None
_last_webhook_parsed_at = None
_last_webhook_user_id = None


def get_webhook_debug_status():
    """Return last webhook timestamps for /api/debug/webhook-status."""
    import datetime
    return {
        "last_received_at": _last_webhook_received_at,
        "last_received_iso": datetime.datetime.fromtimestamp(_last_webhook_received_at).isoformat() if _last_webhook_received_at else None,
        "last_parsed_at": _last_webhook_parsed_at,
        "last_parsed_user_id": _last_webhook_user_id,
        "seconds_since_received": round(time.time() - _last_webhook_received_at, 1) if _last_webhook_received_at else None,
    }


@app.get("/webhook")
async def verify_webhook(request: Request):
    """Endpoint for WhatsApp webhook verification."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    if not VERIFY_TOKEN or VERIFY_TOKEN == "YOUR_SECURE_VERIFY_TOKEN":
        raise HTTPException(status_code=500, detail="WHATSAPP_WEBHOOK_VERIFY_TOKEN must be set in .env")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("WEBHOOK_VERIFIED")
        if challenge is None or (isinstance(challenge, str) and not challenge.strip()):
            raise HTTPException(status_code=400, detail="Invalid webhook challenge")
        try:
            return int(challenge)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid webhook challenge format")
    else:
        raise HTTPException(status_code=403, detail="Verification token mismatch")


@app.post("/webhook")
async def receive_webhook(request: Request):
    """Endpoint for receiving WhatsApp messages from different providers."""
    # Auto-enable debug in local/dev so you can see if webhooks reach the server
    _debug = os.getenv("DEBUG_WEBHOOK_LOGGING", "false").lower() == "true"
    if not _debug and getattr(config, "is_local_env", lambda: False)():
        _debug = True
    if _debug:
        print("\n" + "="*80)
        print("🚨 WEBHOOK HIT DETECTED!")
        print(f"⏰ {datetime.datetime.now()} | IP: {request.client.host if request.client else 'Unknown'}")
        print("="*80)

    global _last_webhook_received_at, _last_webhook_parsed_at, _last_webhook_user_id
    try:
        raw_body = await request.body()
        _last_webhook_received_at = time.time()
        print(f"📥 Webhook POST received ({len(raw_body)} bytes)")
        if _debug:
            print(f"📦 Raw body: {len(raw_body)} bytes")

        try:
            webhook_data = json.loads(raw_body.decode('utf-8'))
        except UnicodeDecodeError:
            webhook_data = json.loads(raw_body.decode('utf-8', errors='ignore'))

        if _debug:
            print(f"Provider: {WhatsAppFactory.get_current_provider()} | Data: {json.dumps(webhook_data, ensure_ascii=False)[:500]}...")
        
        current_provider = WhatsAppFactory.get_current_provider()
        adapter = WhatsAppFactory.get_adapter(current_provider)
        if _debug:
            print(f"Adapter: {type(adapter).__name__}")

        parsed_message = adapter.parse_webhook_message(webhook_data)
        if _debug and parsed_message:
            print(f"Parsed: user_id={parsed_message.get('user_id', 'N/A')} phone={parsed_message.get('phone_number', 'N/A')} message_id={parsed_message.get('message_id', 'N/A')}")
        
        if not parsed_message:
            if not _webhook_is_meta_status_only(webhook_data):
                print("Trying Meta fallback parser...")
            parsed_message = await handle_meta_webhook(webhook_data)
        if not parsed_message:
            parsed_message = _parse_webhook_raw_dict(webhook_data)
        
        # Check for duplicate webhooks (Firestore first = multi-worker safe, then in-memory)
        if parsed_message:
            message_id = parsed_message.get("message_id", "")
            current_time = time.time()

            if message_id:
                if not await _webhook_firestore_try_acquire(message_id):
                    print(f"⚠️ DUPLICATE WEBHOOK (Firestore): message_id={message_id[:64]}...")
                    return JSONResponse(
                        status_code=200,
                        content={"status": "skipped", "reason": "duplicate_webhook", "message_id": message_id},
                    )

            if message_id:
                if not await _webhook_memory_try_claim(message_id, current_time):
                    print(
                        f"⚠️ DUPLICATE WEBHOOK DETECTED (memory): message_id={message_id} "
                        f"(within {WEBHOOK_DEDUP_WINDOW_SECONDS}s window)"
                    )
                    return JSONResponse(
                        status_code=200,
                        content={"status": "skipped", "reason": "duplicate_webhook", "message_id": message_id},
                    )
                print(f"✅ Webhook recorded in dedup cache: {message_id}")

            body_fp = _webhook_text_body_fingerprint(parsed_message)
            if body_fp:
                if not await _webhook_bodyfp_firestore_try_acquire(body_fp, current_time):
                    print(
                        f"⚠️ DUPLICATE WEBHOOK (Firestore body-fp, same text+sender within "
                        f"{WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS}s bucket): body_fp={body_fp[:40]}..."
                    )
                    return JSONResponse(
                        status_code=200,
                        content={
                            "status": "skipped",
                            "reason": "duplicate_inbound_text_firestore",
                            "body_fingerprint_prefix": body_fp[:24],
                        },
                    )
                if not await _webhook_bodyfp_try_claim(body_fp, current_time):
                    print(
                        f"⚠️ DUPLICATE WEBHOOK (same text+sender within {WEBHOOK_TEXT_BODYFP_WINDOW_SECONDS}s): "
                        f"body_fp={body_fp[:40]}..."
                    )
                    return JSONResponse(
                        status_code=200,
                        content={
                            "status": "skipped",
                            "reason": "duplicate_inbound_text_short_window",
                            "body_fingerprint_prefix": body_fp[:24],
                        },
                    )
        
        if parsed_message:
            _last_webhook_parsed_at = time.time()
            _last_webhook_user_id = parsed_message.get("user_id", "")
            print(f"Processing parsed message: {parsed_message}")
            # IMPORTANT: Process in background so we return 200 immediately.
            # MontyMobile throttles/backs off if webhook responses are slow.
            asyncio.ensure_future(process_parsed_message(parsed_message, adapter))
            print("Message queued for processing (background)")
        else:
            if _webhook_is_meta_status_only(webhook_data):
                if os.getenv("DEBUG_WEBHOOK_STATUSES", "false").lower() in ("1", "true", "yes"):
                    print("ℹ️ Webhook: status-only payload (delivered/read); no inbound message to process")
            else:
                print("ERROR: Could not parse webhook from any provider")
                print(f"Webhook keys: {list(webhook_data.keys()) if isinstance(webhook_data, dict) else 'not-dict'}")
                if isinstance(webhook_data, dict) and "entry" in webhook_data:
                    e0 = webhook_data.get("entry", [])
                    if e0 and isinstance(e0, list):
                        print(f"Webhook entry[0] keys: {list(e0[0].keys()) if isinstance(e0[0], dict) else 'N/A'}")

        # Explicit JSONResponse: MontyMobile expects 200 + JSON body. Returning null causes "Response Body: null" in their logs.
        return JSONResponse(status_code=200, content={"status": "success"})
        
    except Exception as e:
        print(f"CRITICAL ERROR processing webhook: {e}")
        import traceback
        traceback.print_exc()
        # Return 200 with error payload to avoid MontyMobile retries on parse/server errors
        return JSONResponse(status_code=200, content={"status": "error", "message": str(e)})


def _webhook_is_meta_status_only(webhook_data: Dict[str, Any]) -> bool:
    """WhatsApp Cloud API sends delivery/read/sent updates with statuses[] and no messages[]."""
    try:
        entries = webhook_data.get("entry") or []
        if not entries or not isinstance(entries, list):
            return False
        entry = entries[0] if isinstance(entries[0], dict) else {}
        changes = entry.get("changes") or []
        if not changes or not isinstance(changes, list):
            return False
        ch = changes[0] if isinstance(changes[0], dict) else {}
        value = ch.get("value") or {}
        if not isinstance(value, dict):
            return False
        msgs = value.get("messages") or []
        return bool(value.get("statuses")) and not msgs
    except Exception:
        return False


def _parse_webhook_raw_dict(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Last-resort: extract from entry/changes/value/messages using raw dict (no Pydantic)."""
    try:
        entries = webhook_data.get("entry") or []
        if not entries or not isinstance(entries, list):
            return None
        entry = entries[0] if isinstance(entries[0], dict) else {}
        changes = entry.get("changes") or []
        if not changes or not isinstance(changes, list):
            return None
        ch = changes[0] if isinstance(changes[0], dict) else {}
        value = ch.get("value") or {}
        if not isinstance(value, dict):
            return None
        if "statuses" in value:
            return None
        messages = value.get("messages") or []
        if not messages or not isinstance(messages, list):
            return None
        msg = messages[0] if isinstance(messages[0], dict) else {}
        _mid = (msg.get("id") or "").strip()
        if not _mid:
            _mid = _synthetic_inbound_id_from_wa_message(msg)
        msg_from = str(msg.get("from") or "").strip()
        if not msg_from:
            contacts = value.get("contacts") or []
            if contacts and isinstance(contacts[0], dict):
                msg_from = str(contacts[0].get("wa_id") or "").strip()
        if not msg_from:
            return None
        phone = f"+{msg_from}" if msg_from and not msg_from.startswith("+") else msg_from
        msg_type = msg.get("type") or "text"
        text_body = (msg.get("text") or {}) if isinstance(msg.get("text"), dict) else {}
        text = str(text_body.get("body") or "")
        if msg_type == "text":
            content = {"text": text}
        elif msg_type == "audio":
            audio_obj = msg.get("audio") or {}
            audio_id = audio_obj.get("id") or audio_obj.get("link") or audio_obj.get("url") or "" if isinstance(audio_obj, dict) else ""
            content = {"audio_id": audio_id}
        elif msg_type == "image":
            img_obj = msg.get("image") or {}
            img_id = img_obj.get("id") or "" if isinstance(img_obj, dict) else ""
            content = {"image_id": img_id}
        else:
            content = {"raw": msg}
        return {
            "user_id": phone,
            "user_name": phone,
            "message_id": f"raw_{_mid}",
            "timestamp": msg.get("timestamp", ""),
            "type": msg_type,
            "content": content,
            "phone_number": phone,
        }
    except Exception as e:
        print(f"Raw webhook parse failed: {e}")
        return None


async def handle_meta_webhook(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle Meta/WhatsApp Cloud API webhook format (fallback)"""
    try:
        request_body = WebhookRequest(**webhook_data)
        
        for entry in request_body.entry:
            for change in entry.changes:
                if change.field == "messages" and change.value.messages:
                    for message in change.value.messages:
                        user_whatsapp_id = message.from_
                        user_name = next((c.profile.name for c in change.value.contacts if c.wa_id == user_whatsapp_id), user_whatsapp_id)
                        
                        return {
                            "user_id": user_whatsapp_id,
                            "user_name": user_name,
                            "message_id": message.id,
                            "timestamp": message.timestamp,
                            "type": message.type,
                            "content": extract_meta_message_content(message)
                        }
        return None
    except Exception as e:
        print(f"Error parsing Meta webhook: {e}")
        return None


def extract_meta_message_content(message) -> Dict[str, Any]:
    """Extract content from Meta message format"""
    if message.type == "text":
        return {"text": message.text.body}
    elif message.type == "image":
        return {"image_id": message.image.id, "caption": getattr(message.image, 'caption', None)}
    elif message.type == "audio":
        return {"audio_id": message.audio.id}
    elif message.type == "video":
        return {"video_id": message.video.id, "caption": getattr(message.video, 'caption', None)}
    elif message.type == "document":
        return {"document_id": message.document.id, "filename": getattr(message.document, 'filename', None)}
    else:
        return {"raw": message.model_dump()}


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, dict):
        return str(content.get("text", "") or "")
    return str(content or "")


def _count_non_empty_lines(text: str) -> int:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return len([line for line in normalized.split("\n") if line.strip()])


def _is_image_attachment(item: Any) -> bool:
    if isinstance(item, str):
        lower = item.lower()
        return lower.startswith("data:image/") or any(
            ext in lower for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif")
        )

    if isinstance(item, dict):
        item_type = str(item.get("type") or item.get("mime_type") or "").lower()
        if "image" in item_type:
            return True
        candidate = (
            item.get("url")
            or item.get("image_id")
            or item.get("image_url")
            or item.get("link")
            or ""
        )
        return _is_image_attachment(candidate)

    return False


def _count_images_in_single_message(message_type: str, content: Any) -> int:
    if isinstance(content, dict):
        for key in ("images", "image_ids", "image_urls"):
            values = content.get(key)
            if isinstance(values, list):
                return sum(1 for item in values if _is_image_attachment(item) or item)

        attachments = content.get("attachments")
        if isinstance(attachments, list):
            return sum(1 for item in attachments if _is_image_attachment(item))

        if content.get("image_id") or content.get("image_url"):
            return 1

    if isinstance(content, list):
        return sum(1 for item in content if _is_image_attachment(item) or item)

    if message_type == "image":
        return 1

    return 0


async def process_parsed_message(parsed_message: Dict[str, Any], adapter):
    """Entry: dedupe same message_id in-process, then delegate."""
    mid_for_dedupe = (parsed_message.get("message_id") or "").strip()
    if mid_for_dedupe:
        if await _process_parsed_should_skip_duplicate(mid_for_dedupe):
            return
    try:
        await _process_parsed_message_impl(parsed_message, adapter)
    except Exception:
        _process_parsed_release_claim_on_error(mid_for_dedupe)
        raise


async def _process_parsed_message_impl(parsed_message: Dict[str, Any], adapter):
    """Process a parsed message regardless of provider. Uses normalized phone as canonical user_id to prevent duplicates."""
    from utils.phone_utils import normalize_phone, is_phone_like_user_id
    from utils.utils import get_canonical_user_id_and_phone, persist_room_to_phone_mapping
    from services.customer_identity_service import resolve_customer_from_external

    raw_user_id = parsed_message["user_id"]
    user_name = parsed_message["user_name"]
    phone_number = parsed_message.get("phone_number")
    # Resolve canonical user_id (E.164 normalized_phone) so same number = same user/thread
    canonical_user_id, normalized_phone = get_canonical_user_id_and_phone(raw_user_id, phone_number)
    user_id = canonical_user_id
    parsed_message["user_id"] = user_id
    parsed_message["phone_number"] = normalized_phone or phone_number or ""

    # Persist room_id -> phone when provider sends room_id but we extracted phone (e.g. Qiscus).
    # Prevents duplicate conversations when same user sends via room_id in future messages.
    if normalized_phone and not is_phone_like_user_id(raw_user_id):
        persist_room_to_phone_mapping(raw_user_id, normalized_phone)

    print(f"DEBUG: identity raw_user_id={raw_user_id} normalized_phone={normalized_phone} canonical_user_id={canonical_user_id}")
    if raw_user_id != canonical_user_id:
        print(f"🔄 Identity resolved: {raw_user_id} → {canonical_user_id}")

    # Migrate in-memory state from raw to canonical so we don't lose conversation_id etc.
    if raw_user_id != user_id and raw_user_id in config.user_data_whatsapp:
        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = dict(config.user_data_whatsapp[raw_user_id])
        else:
            config.user_data_whatsapp[user_id].update(config.user_data_whatsapp[raw_user_id])
        for key in ("user_names", "user_gender", "user_greeting_stage"):
            d = getattr(config, key, None)
            if d and raw_user_id in d and user_id not in d:
                d[user_id] = d[raw_user_id]

    # Per-message guardrails (not conversation-wide): limit text lines and image count.
    message_type = parsed_message.get("type", "")
    content = parsed_message.get("content", {})

    if message_type == "text":
        user_text = _extract_text_from_content(content)
        line_count = _count_non_empty_lines(user_text)
        if line_count > config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE:
            await adapter.send_text_message(
                user_id,
                f"لطفاً خفّف طول الرسالة: الحد الأقصى للرسالة الواحدة هو {config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE} سطر. "
                "قسّمها على أكثر من رسالة قصيرة."
            )
            log_report_event(
                "single_message_text_line_limit_blocked",
                user_name or user_id,
                config.user_gender.get(user_id, "unspecified"),
                {
                    "line_count": line_count,
                    "max_allowed_lines": config.MAX_TEXT_LINES_PER_SINGLE_MESSAGE,
                    "provider": WhatsAppFactory.get_current_provider(),
                },
            )
            return

    image_count = _count_images_in_single_message(message_type, content)
    if image_count > config.MAX_IMAGES_PER_SINGLE_MESSAGE:
        await adapter.send_text_message(
            user_id,
            f"لطفاً قلّل عدد الصور: الحد الأقصى للرسالة الواحدة هو {config.MAX_IMAGES_PER_SINGLE_MESSAGE} صور."
        )
        log_report_event(
            "single_message_image_limit_blocked",
            user_name or user_id,
            config.user_gender.get(user_id, "unspecified"),
            {
                "image_count": image_count,
                "max_allowed_images": config.MAX_IMAGES_PER_SINGLE_MESSAGE,
                "provider": WhatsAppFactory.get_current_provider(),
            },
        )
        return

    # For text: defer external lookup so user message can save+broadcast first (instant in Live Chat)
    defer_external = message_type == "text" and bool(normalized_phone)
    external_exists = None
    if normalized_phone and not defer_external:
        try:
            external = await resolve_customer_from_external(normalized_phone)
            external_exists = bool(external.get("exists"))
            print(f"DEBUG: external_lookup normalized_phone={normalized_phone} exists={external.get('exists')} name={external.get('name')}")
            if external.get("exists") and external.get("name"):
                config.user_names[user_id] = external["name"]
                user_name = external["name"]
                parsed_message["user_name"] = user_name
            else:
                config.user_names.pop(user_id, None)
                user_name = ""
                parsed_message["user_name"] = user_name
            if external.get("gender") and external["gender"] in ("male", "female"):
                config.user_gender[user_id] = external["gender"]
                if config.user_greeting_stage.get(user_id, 0) <= 1:
                    config.user_greeting_stage[user_id] = 2
        except Exception as e:
            print(f"WARNING: External resolve failed for {normalized_phone}: {e}; using phone only")
            config.user_names.pop(user_id, None)
            parsed_message["user_name"] = ""
    elif defer_external:
        user_name = parsed_message.get("user_name") or config.user_names.get(user_id) or ""
        parsed_message["user_name"] = user_name
        # Resolve CRM name in background (user message will show in Live Chat immediately)
        async def _set_name_from_external():
            try:
                ext = await resolve_customer_from_external(normalized_phone)
                user_state = config.user_data_whatsapp.get(user_id)
                if user_state is not None:
                    user_state["crm_customer_exists"] = bool(ext.get("exists"))
                    user_state["customer_file_status"] = "existing_file" if ext.get("exists") else "new_customer"
                if ext.get("exists") and ext.get("name"):
                    config.user_names[user_id] = ext["name"]
                else:
                    config.user_names.pop(user_id, None)
                if ext.get("gender") and ext["gender"] in ("male", "female"):
                    config.user_gender[user_id] = ext["gender"]
            except Exception:
                pass
        asyncio.create_task(_set_name_from_external())

    message_type = parsed_message["type"]
    content = parsed_message["content"]

    # Initialize user_data_whatsapp if not exists (AI Smart Employee state schema)
    if user_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_id] = {
            'user_preferred_lang': 'ar',
            'initial_user_query_to_process': None,
            'awaiting_human_handover_confirmation': False,
            'current_conversation_id': None,
            'crm_customer_exists': None,
            'customer_file_status': None,
            **config.DEFAULT_CONVERSATION_STATE,
        }
        print(f"✅ Initialized user_data_whatsapp for user {user_id}")
    
    # Store phone number IMMEDIATELY
    if phone_number:
        config.user_data_whatsapp[user_id]["phone_number"] = phone_number
        print(f"✅ CRITICAL: Stored phone_number {phone_number} for user {user_id} BEFORE any processing")
    else:
        print(f"⚠️ WARNING: No phone_number extracted for user {user_id}")

    if external_exists is not None:
        config.user_data_whatsapp[user_id]["crm_customer_exists"] = external_exists
        config.user_data_whatsapp[user_id]["customer_file_status"] = "existing_file" if external_exists else "new_customer"

    # Persist source message id as one-shot metadata for Firestore dedupe.
    source_message_id = parsed_message.get("message_id")
    if source_message_id:
        config.user_data_whatsapp[user_id]["_source_message_id"] = str(source_message_id)
    else:
        config.user_data_whatsapp[user_id].pop("_source_message_id", None)

    # Collect webhook text body fingerprints for cross-worker AI turn claim (same text, different wamid).
    if message_type == "text":
        _tbfp = _webhook_text_body_fingerprint(parsed_message)
        if _tbfp:
            config.user_data_whatsapp[user_id].setdefault("_batch_turn_body_fps", []).append(_tbfp)

    # ===== RESTORE USER STATE FROM FIRESTORE FIRST (handles server restart) =====
    # Always try to restore from Firestore before API lookup
    # Only restore if gender is not already set to a valid value
    current_gender = config.user_gender.get(user_id)
    print(f"🔍 DEBUG: Before Firestore restore - current_gender in memory: '{current_gender}'")
    if current_gender not in ["male", "female"]:
        try:
            from utils.utils import get_user_state_from_firestore
            print(f"🔄 Attempting to restore user state from Firestore for {user_id}...")
            firestore_state = await get_user_state_from_firestore(user_id)
            print(f"🔍 DEBUG: Firestore returned state: {firestore_state}")

            if firestore_state:
                # Restore gender if valid
                firestore_gender = firestore_state.get("gender", "")
                if firestore_gender in ["male", "female"]:
                    config.user_gender[user_id] = firestore_gender
                    print(f"✅ Restored gender from Firestore: {firestore_gender}")

                # Restore greeting stage if > 0
                firestore_greeting_stage = firestore_state.get("greeting_stage", 0)
                if firestore_greeting_stage > 0:
                    config.user_greeting_stage[user_id] = firestore_greeting_stage
                    print(f"✅ Restored greeting_stage from Firestore: {firestore_greeting_stage}")

                # Restore name if available
                firestore_name = firestore_state.get("name", "")
                if firestore_name and firestore_name != "Unknown Customer":
                    config.user_names[user_id] = firestore_name
                    user_name = firestore_name
                    print(f"✅ Restored name from Firestore: {firestore_name}")
            else:
                print(f"ℹ️ No user state found in Firestore for {user_id}")
        except Exception as e:
            print(f"❌ Error restoring user state from Firestore: {e}")
            import traceback
            traceback.print_exc()

    # Debug: Log state after Firestore restoration attempt
    print(f"🔍 DEBUG: After Firestore restore - gender: '{config.user_gender.get(user_id)}', greeting_stage: {config.user_greeting_stage.get(user_id, 0)}")

    # (Name/gender from external CRM are already set above via resolve_customer_from_external)

    # New-user inbound messages should not auto-trigger /start welcome.
    # Session greeting is now handled in handle_message based on conversation/inactivity policy.
    is_new_user = (
        user_id not in config.user_names or
        user_id not in config.user_greeting_stage or
        config.user_greeting_stage.get(user_id, 0) == 0
    )
    if is_new_user:
        print(f"🆕 NEW USER detected: {user_id}, using session greeting flow (no auto /start).")
        config.user_greeting_stage[user_id] = max(config.user_greeting_stage.get(user_id, 0), 1)
        if config.user_gender.get(user_id) not in ["male", "female"]:
            config.user_gender[user_id] = "unknown"
    else:
        print(f"👤 EXISTING USER: {user_id}, normal flow.")

    # Handle different message types
    if message_type == "text":
        # Handle both dict format (old) and string format (new)
        if isinstance(content, dict):
            user_input_text = content.get("text", "")
        else:
            user_input_text = str(content)
        
        if config.user_data_whatsapp.get(user_id, {}).get("awaiting_post_session_feedback_rating"):
            from services.post_session_feedback_rating_service import (
                try_handle_post_session_feedback_reply,
            )

            if await try_handle_post_session_feedback_reply(user_id, user_input_text, adapter):
                return

        if config.user_data_whatsapp.get(user_id, {}).get("awaiting_session_rating"):
            from services.session_rating_service import try_handle_session_rating_reply

            if await try_handle_session_rating_reply(user_id, user_input_text, adapter):
                return

        if user_input_text.lower() == "/exit":
            await exit_training_mode_whatsapp(user_id)
        elif user_input_text.lower() == "/daily_report":
            await generate_daily_report_command_whatsapp(user_id)
        elif user_input_text.lower() == "/takeover":
            current_conv_id = config.user_data_whatsapp[user_id].get('current_conversation_id')
            if current_conv_id:
                await set_human_takeover_status(
                    user_id,
                    current_conv_id,
                    True,
                    None,
                    None,
                    None,
                    True,  # force_waiting_queue (admin /takeover)
                )
                await adapter.send_text_message(user_id, "تم تفعيل وضع التحكم البشري لهذه المحادثة. البوت لن يرد عليها.")
            else:
                await adapter.send_text_message(user_id, "لا توجد محادثة جارية لتفعيل التحكم البشري عليها.")
        elif user_input_text.lower() == "/release":
            current_conv_id = config.user_data_whatsapp[user_id].get('current_conversation_id')
            if current_conv_id:
                await set_human_takeover_status(user_id, current_conv_id, False)
                await adapter.send_text_message(user_id, "تم إلغاء وضع التحكم البشري لهذه المحادثة. البوت سيعود للرد.")
            else:
                await adapter.send_text_message(user_id, "لا توجد محادثة جارية لإلغاء التحكم البشري عليها.")
        else:
            await handle_message_whatsapp_with_adapter(user_id, user_input_text, user_name, adapter, phone_number)
            
    elif message_type == "image":
        image_id = content.get("image_id")
        if image_id:
            # Process image with GPT-4 Vision analysis for all providers
            print(f"DEBUG: Image received - processing with GPT-4 Vision analysis")
            await handle_photo_message_whatsapp_with_adapter(user_id, image_id, user_name, adapter)
            
    elif message_type in ("audio", "voice", "ptt"):
        audio_id = None
        if isinstance(content, dict):
            audio_id = content.get("audio_id") or content.get("link") or content.get("url")
        elif isinstance(content, str) and content.strip():
            audio_id = content.strip()
        if audio_id:
            await handle_voice_message_whatsapp_with_adapter(user_id, audio_id, user_name, adapter)
        else:
            print(f"⚠️ Audio/voice message received but no audio_id/link: content={type(content).__name__}")
            
    elif message_type == "file_attachment":
        file_url = content.get("image_id") or content.get("audio_id") or content.get("document_id")
        if file_url:
            if content.get("image_id"):
                await handle_photo_message_whatsapp_with_adapter(user_id, file_url, user_name, adapter)
            elif content.get("audio_id"):
                await handle_voice_message_whatsapp_with_adapter(user_id, file_url, user_name, adapter)
            else:
                await adapter.send_text_message(user_id, "تم استلام الملف، شكراً لك!")
                
    else:
        await adapter.send_text_message(user_id, "عذراً، أنا أستطيع معالجة الرسائل النصية، الصور، والرسائل الصوتية فقط حالياً. 😅")
        print(f"Unhandled message type: {message_type} from {user_id}")

    # Clear one-shot source ID if it wasn't consumed in handlers.
    config.user_data_whatsapp.get(user_id, {}).pop("_source_message_id", None)


# ============================================================================
# WhatsApp Adapter Functions
# ============================================================================

# Import these after function definitions to avoid circular imports
import datetime
from config import TRAINER_WHATSAPP_NUMBER
from services.api_integrations import generate_daily_report_command


async def start_command_whatsapp(user_whatsapp_id: str, user_name: str):
    """Adapts start_command for WhatsApp."""
    print(f"DEBUG: start_command_whatsapp called for user {user_whatsapp_id}")

    config.user_names[user_whatsapp_id] = user_name

    config.user_context[user_whatsapp_id].clear()
    config.gender_attempts[user_whatsapp_id] = 0
    config.user_last_bot_response_time[user_whatsapp_id] = datetime.datetime.now()
    config.user_in_training_mode[user_whatsapp_id] = False
    config.user_photo_analysis_count[user_whatsapp_id] = 0
    config.user_in_human_takeover_mode[user_whatsapp_id] = False

    # FIX: Use .get() to properly check for existing gender value
    # This preserves gender that was set from API in process_parsed_message
    existing_gender = config.user_gender.get(user_whatsapp_id)
    if existing_gender and existing_gender in ["male", "female"]:
        config.user_greeting_stage[user_whatsapp_id] = 2  # Skip gender question
        print(f"✅ Gender already set (preserving): {existing_gender}")
    else:
        config.user_gender[user_whatsapp_id] = "unknown"  # Use "unknown" for consistency
        config.user_greeting_stage[user_whatsapp_id] = 1  # Ask for gender
        print(f"ℹ️ Gender not found, will ask user")

    if user_whatsapp_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_whatsapp_id] = {}

    config.user_data_whatsapp[user_whatsapp_id]['user_preferred_lang'] = 'ar'
    config.user_data_whatsapp[user_whatsapp_id]['initial_user_query_to_process'] = None
    config.user_data_whatsapp[user_whatsapp_id]['awaiting_human_handover_confirmation'] = False
    config.user_data_whatsapp[user_whatsapp_id]['current_conversation_id'] = None

    initial_message = config.WELCOME_MESSAGES.get(
        config.user_data_whatsapp[user_whatsapp_id]['user_preferred_lang'],
        config.WELCOME_MESSAGES['ar']
    )

    # Use current provider's adapter (MontyMobile/Meta/etc.) - not hardcoded Meta
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)
    await adapter.send_text_message(user_whatsapp_id, initial_message)

    # NOTE: Removed call to start_command() to prevent:
    # 1. Duplicate welcome messages
    # 2. Potential gender reset
    # All initialization is now done in this function

    print(f"DEBUG: start_command_whatsapp ended for user {user_whatsapp_id}. Stage: {config.user_greeting_stage[user_whatsapp_id]}, Gender: '{config.user_gender.get(user_whatsapp_id, 'unknown')}'")


async def handle_message_whatsapp_with_adapter(user_id: str, user_input_text: str, user_name: str, adapter, phone_number: str = None):
    """Handle message with specific adapter"""
    if user_id not in config.user_data_whatsapp:
        config.user_data_whatsapp[user_id] = {
            'user_preferred_lang': 'ar', 
            'initial_user_query_to_process': None, 
            'awaiting_human_handover_confirmation': False, 
            'current_conversation_id': None
        }

    if phone_number:
        config.user_data_whatsapp[user_id]['phone_number'] = phone_number
        print(f"✅ DEBUG: Stored phone_number {phone_number} for user {user_id}")
    else:
        print(f"❌ CRITICAL: No phone_number extracted for user {user_id}!")
        config.user_data_whatsapp[user_id]['phone_number'] = None

    _same_turn_text_sends = set()

    async def adapter_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
        if message_text:
            from services.whatsapp_adapters.outbound_text_dedupe import outbound_fingerprint

            fp = outbound_fingerprint(
                to_number,
                message_text,
                phone_hint=phone_number or config.user_data_whatsapp.get(user_id, {}).get("phone_number"),
            )
            if fp and fp in _same_turn_text_sends:
                tid = config.user_data_whatsapp.get(user_id, {}).get("_ai_turn_trace_id", "?")
                print(
                    f"⚠️ [whatsapp-send] trace_id={tid} dedupe=same_turn_suppressed "
                    f"user={user_id[:16]}… text_len={len(message_text)}"
                )
                return {"success": True, "deduped_same_turn": True}
            result = await adapter.send_text_message(to_number, message_text)
            tid = config.user_data_whatsapp.get(user_id, {}).get("_ai_turn_trace_id", "?")
            if result:
                if result.get("deduped_outbound"):
                    print(
                        f"[whatsapp-send] trace_id={tid} dedupe=global_window user={user_id[:12]}… "
                        f"text_len={len(message_text)}"
                    )
                elif (
                    result.get("success")
                    and not result.get("dry_run")
                    and os.getenv("TRACE_AI_OUTBOUND", "").lower() in ("1", "true", "yes")
                ):
                    print(
                        f"[whatsapp-send] trace_id={tid} sent=ok user={user_id[:12]}… "
                        f"text_len={len(message_text)}"
                    )
            if fp and result and result.get("success"):
                _same_turn_text_sends.add(fp)
            return result
        elif image_url:
            return await adapter.send_image_message(to_number, image_url)
        elif audio_url:
            return await adapter.send_audio_message(to_number, audio_url)
        return False

    from modules.whatsapp_adapters import send_whatsapp_typing_indicator
    await handle_message(
        user_id=user_id,
        user_name=user_name,
        user_input_text=user_input_text,
        user_data=config.user_data_whatsapp[user_id],
        send_message_func=adapter_send_message,
        send_action_func=send_whatsapp_typing_indicator
    )
    await await_whatsapp_delayed_processing(user_id)


async def _extract_image_base64_and_format(image_url: str, headers: Optional[Dict[str, str]] = None) -> tuple:
    """Extract base64 string and format from image_url (data: or http)."""
    import base64
    if image_url.startswith("data:image/"):
        parts = image_url.split(",", 1)
        if len(parts) != 2:
            raise ValueError("Invalid data URL format")
        mime_part = parts[0]
        base64_data = parts[1]
        fmt = mime_part.replace("data:image/", "").replace(";base64", "").strip()
        if fmt == "jpg":
            fmt = "jpeg"
        return base64_data, fmt or "jpeg"
    async with httpx.AsyncClient() as client:
        resp = await client.get(image_url, headers=headers or {}, timeout=30)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "").lower()
        image_bytes = resp.content
    magic = image_bytes[:12] if len(image_bytes) >= 12 else image_bytes
    if magic[:3] == b'\xff\xd8\xff':
        fmt = "jpeg"
    elif magic[:4] == b'\x89PNG':
        fmt = "png"
    elif magic[:6] in (b'GIF87a', b'GIF89a'):
        fmt = "gif"
    elif len(magic) >= 12 and magic[:4] == b'RIFF' and magic[8:12] == b'WEBP':
        fmt = "webp"
    else:
        fmt = "jpeg" if ("jpeg" in content_type or "jpg" in content_type) else "png" if "png" in content_type else "jpeg"
    return base64.b64encode(image_bytes).decode("utf-8"), fmt


async def handle_photo_message_whatsapp_with_adapter(user_id: str, image_id: str, user_name: str, adapter):
    """Handle photo message: route image to main AI flow (no photo_analysis_service)."""
    try:
        current_provider = WhatsAppFactory.get_current_provider()
        
        print(f"DEBUG: Handling photo message - provider: {current_provider}, image_id: {image_id}")
        
        if current_provider == "qiscus":
            print(f"DEBUG: Using Qiscus provider - image_id is URL")
            image_url = image_id
        elif current_provider == "montymobile":
            print(f"DEBUG: Using MontyMobile provider - downloading media via MontyMobile API")
            
            # Use MontyMobile's media download endpoint
            # Based on their documentation: GET https://notification-qa.montylocal.net/api/v1/Push/external/{media_id}
            # Production endpoint should be similar pattern
            try:
                # MontyMobile media download endpoint (CORRECT - as provided by MontyMobile support)
                media_api_url = f"{adapter.base_url}/api/v2/WhatsappApi/get-media?MediaId={image_id}"
                
                montymobile_headers = {
                    "Tenant": adapter.tenant_id,
                    "api-key": adapter.api_token
                }
                
                print(f"DEBUG: Downloading media from MontyMobile API: {media_api_url}")
                print(f"DEBUG: Using Tenant: {adapter.tenant_id}")
                
                async with httpx.AsyncClient() as client:
                    # Download the media file directly
                    media_response = await client.get(media_api_url, headers=montymobile_headers, timeout=30)
                    media_response.raise_for_status()
                    
                    # Detect image format from content-type header or magic bytes
                    content_type = media_response.headers.get('content-type', '').lower()
                    print(f"DEBUG: Media response content-type: {content_type}")
                    print(f"DEBUG: Media response size: {len(media_response.content)} bytes")
                    
                    # Check if response is JSON (MontyMobile returns JSON with image data inside)
                    if 'application/json' in content_type:
                        print(f"DEBUG: Response is JSON, extracting image data...")
                        media_json = media_response.json()
                        print(f"DEBUG: JSON keys: {list(media_json.keys())}")
                        
                        # Extract the actual image data from JSON
                        # MontyMobile might return base64 data or a URL
                        if 'data' in media_json:
                            image_data_field = media_json['data']
                            if isinstance(image_data_field, str):
                                # It's base64 encoded
                                import base64
                                image_bytes = base64.b64decode(image_data_field)
                                print(f"DEBUG: Decoded base64 image from JSON, size: {len(image_bytes)} bytes")
                            elif isinstance(image_data_field, dict):
                                # It's a nested object, check for base64 or URL inside
                                print(f"DEBUG: data field is dict with keys: {list(image_data_field.keys())}")
                                # MontyMobile returns {"data": {"data": "base64string"}}
                                if 'data' in image_data_field and isinstance(image_data_field['data'], str):
                                    # The actual base64 data is in data.data
                                    import base64
                                    image_bytes = base64.b64decode(image_data_field['data'])
                                    print(f"DEBUG: Decoded base64 image from nested data.data, size: {len(image_bytes)} bytes")
                                elif 'base64' in image_data_field or 'content' in image_data_field or 'file' in image_data_field:
                                    # Try different possible field names
                                    base64_data = image_data_field.get('base64') or image_data_field.get('content') or image_data_field.get('file')
                                    if base64_data:
                                        import base64
                                        image_bytes = base64.b64decode(base64_data)
                                        print(f"DEBUG: Decoded base64 image from nested JSON, size: {len(image_bytes)} bytes")
                                    else:
                                        print(f"DEBUG: Full data object: {json.dumps(image_data_field, indent=2)[:500]}...")
                                        raise ValueError(f"Could not find base64 data in nested object")
                                elif 'url' in image_data_field:
                                    image_url_from_json = image_data_field['url']
                                    print(f"DEBUG: Found URL in nested data object, downloading from: {image_url_from_json}")
                                    image_response = await client.get(image_url_from_json, timeout=30)
                                    image_response.raise_for_status()
                                    image_bytes = image_response.content
                                else:
                                    print(f"DEBUG: Full data object: {json.dumps(image_data_field, indent=2)}")
                                    raise ValueError(f"Could not find image data in nested object")
                            else:
                                print(f"DEBUG: Unexpected data format in JSON: {type(image_data_field)}")
                                raise ValueError(f"Unexpected image data format in JSON response")
                        elif 'url' in media_json:
                            # It's a URL, download from there
                            image_url_from_json = media_json['url']
                            print(f"DEBUG: Found URL in JSON, downloading from: {image_url_from_json}")
                            image_response = await client.get(image_url_from_json, timeout=30)
                            image_response.raise_for_status()
                            image_bytes = image_response.content
                        else:
                            print(f"DEBUG: Full JSON response: {json.dumps(media_json, indent=2)}")
                            raise ValueError(f"Could not find image data in JSON response")
                    else:
                        # Response is raw binary image
                        image_bytes = media_response.content
                        print(f"DEBUG: Response is raw binary image")
                    
                    # Detect format from magic bytes (first few bytes of file)
                    magic_bytes = image_bytes[:8]
                    print(f"DEBUG: First 8 bytes (hex): {magic_bytes.hex()}")
                    
                    # Determine image format
                    if magic_bytes.startswith(b'\xff\xd8\xff'):
                        image_format = 'jpeg'
                    elif magic_bytes.startswith(b'\x89PNG'):
                        image_format = 'png'
                    elif magic_bytes.startswith(b'GIF87a') or magic_bytes.startswith(b'GIF89a'):
                        image_format = 'gif'
                    elif magic_bytes.startswith(b'RIFF') and magic_bytes[8:12] == b'WEBP':
                        image_format = 'webp'
                    else:
                        # Fallback to content-type
                        if 'jpeg' in content_type or 'jpg' in content_type:
                            image_format = 'jpeg'
                        elif 'png' in content_type:
                            image_format = 'png'
                        elif 'gif' in content_type:
                            image_format = 'gif'
                        elif 'webp' in content_type:
                            image_format = 'webp'
                        else:
                            image_format = 'jpeg'  # Default fallback
                    
                    print(f"DEBUG: Detected image format: {image_format}")
                    
                    # Convert to base64 for processing (use image_bytes, not media_response.content!)
                    import base64
                    base64_image = base64.b64encode(image_bytes).decode("utf-8")
                    print(f"DEBUG: Encoded image to base64, size: {len(base64_image)} bytes")
                    
                    # Create a data URL for the photo handler with correct format
                    image_url = f"data:image/{image_format};base64,{base64_image}"
                    print(f"DEBUG: Created base64 data URL for image processing with format: {image_format}")
                    
            except Exception as e:
                print(f"ERROR: Failed to download media from MontyMobile: {e}")
                import traceback
                traceback.print_exc()
                raise
        else:
            print(f"DEBUG: Using Meta/Facebook provider - fetching from Graph API")
            response = await whatsapp_api_client.get(f"/{image_id}/", headers={"Authorization": f"Bearer {WHATSAPP_API_TOKEN}"})
            response.raise_for_status()
            image_data = response.json()
            image_url = image_data.get("url")
            if not image_url:
                raise ValueError("Image URL not found in API response.")

        download_headers = {"Authorization": f"Bearer {WHATSAPP_API_TOKEN}"} if current_provider not in ("qiscus", "montymobile") else None

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar', 
                'initial_user_query_to_process': None, 
                'awaiting_human_handover_confirmation': False, 
                'current_conversation_id': None
            }

        user_data = config.user_data_whatsapp[user_id]
        base64_image, image_format = await _extract_image_base64_and_format(image_url, headers=download_headers)

        if config.user_in_training_mode.get(user_id, False):
            image_url_for_training = f"data:image/{image_format};base64,{base64_image}"
            async def adapter_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
                if message_text:
                    return await adapter.send_text_message(to_number, message_text)
                elif image_url:
                    return await adapter.send_image_message(to_number, image_url)
                elif audio_url:
                    return await adapter.send_audio_message(to_number, audio_url)
                return False
            from modules.whatsapp_adapters import send_whatsapp_typing_indicator
            await handle_training_input(
                user_id=user_id, user_name=user_name, image_url=image_url_for_training,
                user_data=user_data, send_message_func=adapter_send_message, send_action_func=send_whatsapp_typing_indicator
            )
            return

        source_message_id = user_data.pop("_source_message_id", None)
        image_metadata = {"type": "image"}
        if source_message_id:
            image_metadata["source_message_id"] = source_message_id
        from services.outbound_turn_idempotency import (
            record_inbound_mid_for_ai_turn,
            stable_ai_claim_identity,
            try_claim_ai_turn,
        )

        record_inbound_mid_for_ai_turn(user_data, source_message_id)
        await save_conversation_message_to_firestore(
            user_id, "user", "[صورة]",
            user_data.get('current_conversation_id'),
            user_name, user_data.get('phone_number'),
            metadata=image_metadata
        )

        async def adapter_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
            if message_text:
                return await adapter.send_text_message(to_number, message_text)
            elif image_url:
                return await adapter.send_image_message(to_number, image_url)
            elif audio_url:
                return await adapter.send_audio_message(to_number, audio_url)
            return False

        from modules.whatsapp_adapters import send_whatsapp_typing_indicator
        user_data["_ai_turn_trace_id"] = str(uuid.uuid4())
        trace = user_data["_ai_turn_trace_id"]
        user_data.pop("_batch_turn_body_fps", None)
        mids = user_data.pop("_batch_inbound_mids", []) or []
        claim_id = stable_ai_claim_identity(user_id, user_data.get("phone_number"))
        if mids and not await try_claim_ai_turn(claim_id, mids):
            print(
                f"⚠️ [ai-turn] trace_id={trace} image claim=DUPLICATE_SKIP user={user_id[:20]}…"
            )
            return
        if mids:
            print(
                f"[ai-turn] trace_id={trace} image claim=OK claim_key={claim_id[:20]}… mids_n={len(mids)}"
            )
        else:
            print(
                f"[ai-turn] trace_id={trace} image claim=SKIPPED(no_inbound_mids) — "
                f"add TRACE or check provider message ids"
            )
        await _process_and_respond(
            user_id=user_id,
            user_name=user_name,
            user_input_to_process="[صورة]",
            user_data=user_data,
            send_message_func=adapter_send_message,
            send_action_func=send_whatsapp_typing_indicator,
            user_image_base64=base64_image,
            user_image_format=image_format,
        )

    except Exception as e:
        print(f"ERROR processing image {image_id} for user {user_id}: {e}")
        error_reply = "عذراً، واجهت مشكلة في معالجة صورتك. الرجاء المحاولة مرة أخرى."
        await adapter.send_text_message(user_id, error_reply)
        log_report_event("whatsapp_media_download_failed", user_name, config.user_gender.get(user_id, "unspecified"), {"media_type": "image", "error": str(e)})
        try:
            from services.interaction_flow_logger import log_interaction, is_flow_logging_enabled
            if is_flow_logging_enabled():
                log_interaction(
                    user_id, "[صورة]", error_reply, "gpt",
                    user_name=user_name, user_phone=config.user_data_whatsapp.get(user_id, {}).get("phone_number"),
                    user_gender=config.user_gender.get(user_id, "unknown"),
                    flow_steps=[
                        {"step": 1, "title": "Image received", "content": "User sent image.", "event_type": "image_received", "status": "success"},
                        {"step": 2, "title": "Image download/prepare failed", "content": str(e), "event_type": "error", "status": "error"},
                        {"step": 3, "title": "Bot → User (fallback)", "content": error_reply, "event_type": "fallback_triggered"},
                    ],
                    flow_error=str(e), message_type="image",
                )
        except Exception as log_err:
            print(f"⚠️ Could not log image error to Activity Flow: {log_err}")


async def handle_voice_message_whatsapp_with_adapter(user_id: str, audio_id: str, user_name: str, adapter):
    """Handle voice message with specific adapter"""
    try:
        current_provider = WhatsAppFactory.get_current_provider()
        
        print(f"DEBUG: Handling audio message - provider: {current_provider}, audio_id: {audio_id}")
        
        # Extract audio URL based on provider
        audio_url = None
        if current_provider == "qiscus":
            # For Qiscus, audio_id IS the full URL
            print(f"DEBUG: Using Qiscus provider - audio_id is URL")
            audio_url = audio_id
            async with httpx.AsyncClient() as client:
                audio_content_response = await client.get(audio_id)
                audio_content_response.raise_for_status()
                audio_data_bytes = io.BytesIO(audio_content_response.content)
                audio_data_bytes.seek(0)
        elif current_provider == "montymobile":
            print(f"DEBUG: Using MontyMobile provider - downloading audio via MontyMobile API")
            
            try:
                # MontyMobile media download endpoint (same as images)
                media_api_url = f"{adapter.base_url}/api/v2/WhatsappApi/get-media?MediaId={audio_id}"
                
                montymobile_headers = {
                    "Tenant": adapter.tenant_id,
                    "api-key": adapter.api_token
                }
                
                print(f"DEBUG: Downloading audio from MontyMobile API: {media_api_url}")
                print(f"DEBUG: Using Tenant: {adapter.tenant_id}")
                
                async with httpx.AsyncClient() as client:
                    # Download the media file
                    media_response = await client.get(media_api_url, headers=montymobile_headers, timeout=30)
                    media_response.raise_for_status()
                    
                    content_type = media_response.headers.get('content-type', '').lower()
                    print(f"DEBUG: Audio response content-type: {content_type}")
                    print(f"DEBUG: Audio response size: {len(media_response.content)} bytes")
                    
                    # Check if response is JSON (MontyMobile returns JSON with audio data inside)
                    if 'application/json' in content_type:
                        print(f"DEBUG: Response is JSON, extracting audio data...")
                        media_json = media_response.json()
                        print(f"DEBUG: JSON keys: {list(media_json.keys())}")
                        
                        # Extract the actual audio data from JSON (same structure as images)
                        if 'data' in media_json:
                            audio_data_field = media_json['data']
                            if isinstance(audio_data_field, str):
                                # It's base64 encoded
                                import base64
                                audio_bytes = base64.b64decode(audio_data_field)
                                print(f"DEBUG: Decoded base64 audio from JSON, size: {len(audio_bytes)} bytes")
                            elif isinstance(audio_data_field, dict):
                                # It's a nested object
                                print(f"DEBUG: data field is dict with keys: {list(audio_data_field.keys())}")
                                # MontyMobile returns {"data": {"data": "base64string"}}
                                if 'data' in audio_data_field and isinstance(audio_data_field['data'], str):
                                    # The actual base64 data is in data.data
                                    import base64
                                    audio_bytes = base64.b64decode(audio_data_field['data'])
                                    print(f"DEBUG: Decoded base64 audio from nested data.data, size: {len(audio_bytes)} bytes")
                                elif 'url' in audio_data_field:
                                    audio_url_from_json = audio_data_field['url']
                                    print(f"DEBUG: Found URL in nested data object, downloading from: {audio_url_from_json}")
                                    audio_response = await client.get(audio_url_from_json, timeout=30)
                                    audio_response.raise_for_status()
                                    audio_bytes = audio_response.content
                                else:
                                    print(f"DEBUG: Full data object: {json.dumps(audio_data_field, indent=2)[:500]}...")
                                    raise ValueError(f"Could not find audio data in nested object")
                            else:
                                print(f"DEBUG: Unexpected data format in JSON: {type(audio_data_field)}")
                                raise ValueError(f"Unexpected audio data format in JSON response")
                        elif 'url' in media_json:
                            # It's a URL, download from there
                            audio_url_from_json = media_json['url']
                            print(f"DEBUG: Found URL in JSON, downloading from: {audio_url_from_json}")
                            audio_response = await client.get(audio_url_from_json, timeout=30)
                            audio_response.raise_for_status()
                            audio_bytes = audio_response.content
                        else:
                            print(f"DEBUG: Full JSON response: {json.dumps(media_json, indent=2)[:500]}...")
                            raise ValueError(f"Could not find audio data in JSON response")
                    else:
                        # Response is raw binary audio
                        audio_bytes = media_response.content
                        print(f"DEBUG: Response is raw binary audio")
                    
                    # Create BytesIO object for audio processing
                    audio_data_bytes = io.BytesIO(audio_bytes)
                    audio_data_bytes.seek(0)
                    print(f"DEBUG: Created BytesIO object for audio processing")

                    # Upload audio to Firebase Storage to get a playable URL for the dashboard
                    try:
                        import base64
                        from utils.utils import upload_base64_to_firebase_storage

                        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                        file_name = f"voice_{user_id}_{audio_id[:8]}.ogg"

                        audio_url = await upload_base64_to_firebase_storage(
                            audio_base64,
                            file_name,
                            file_type="audio/ogg"
                        )

                        if audio_url:
                            print(f"DEBUG: Uploaded audio to Firebase Storage: {audio_url}")
                        else:
                            print(f"DEBUG: Failed to upload audio to Firebase Storage, audio_url will be None")
                    except Exception as upload_error:
                        print(f"WARNING: Failed to upload audio to Firebase Storage: {upload_error}")
                        audio_url = None
                    
            except Exception as e:
                print(f"ERROR: Failed to download audio from MontyMobile: {e}")
                import traceback
                traceback.print_exc()
                raise
        else:
            # For Meta/360Dialog, get URL from API response
            print(f"DEBUG: Using Meta/Facebook provider - fetching from Graph API")
            response = await whatsapp_api_client.get(f"/{audio_id}/", headers={"Authorization": f"Bearer {WHATSAPP_API_TOKEN}"})
            response.raise_for_status()
            audio_data = response.json()
            audio_url = audio_data.get("url")
            if not audio_url:
                raise ValueError("Audio URL not found in API response.")

            async with httpx.AsyncClient() as client:
                audio_content_response = await client.get(audio_url)
                audio_content_response.raise_for_status()
                audio_data_bytes = io.BytesIO(audio_content_response.content)
                audio_data_bytes.seek(0)

        if user_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_id] = {
                'user_preferred_lang': 'ar', 
                'initial_user_query_to_process': None, 
                'awaiting_human_handover_confirmation': False, 
                'current_conversation_id': None
            }

        async def adapter_send_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
            if message_text:
                return await adapter.send_text_message(to_number, message_text)
            elif image_url:
                return await adapter.send_image_message(to_number, image_url)
            elif audio_url:
                return await adapter.send_audio_message(to_number, audio_url)
            return False

        from modules.whatsapp_adapters import send_whatsapp_typing_indicator
        # ✅ CRITICAL FIX: Pass audio_url to handle_voice_message so it gets saved to Firebase
        await handle_voice_message(
            user_id=user_id,
            user_name=user_name,
            audio_data_bytes=audio_data_bytes,
            user_data=config.user_data_whatsapp[user_id],
            send_message_func=adapter_send_message,
            send_action_func=send_whatsapp_typing_indicator,
            audio_url=audio_url  # ✅ NEW: Pass the URL so voice message has type="voice" + audio_url in Firebase
        )
        await await_whatsapp_delayed_processing(user_id)

    except Exception as e:
        print(f"ERROR processing audio {audio_id} for user {user_id}: {e}")
        await adapter.send_text_message(user_id, "عذراً، واجهت مشكلة في معالجة رسالتك الصوتية. الرجاء المحاولة مرة أخرى.")
        log_report_event("whatsapp_media_download_failed", user_name, config.user_gender.get(user_id, "unspecified"), {"media_type": "audio", "error": str(e)})


async def start_training_mode_whatsapp(user_whatsapp_id: str):
    """Adapts start_training_mode for WhatsApp."""
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)

    async def _adapter_send(to: str, msg: str = None, img: str = None, aud: str = None):
        if msg:
            return await adapter.send_text_message(to, msg)
        elif img:
            return await adapter.send_image_message(to, img)
        elif aud:
            return await adapter.send_audio_message(to, aud)
        return False

    if user_whatsapp_id == TRAINER_WHATSAPP_NUMBER:
        if user_whatsapp_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_whatsapp_id] = {'user_preferred_lang': 'ar', 'initial_user_query_to_process': None, 'awaiting_human_handover_confirmation': False, 'current_conversation_id': None}

        from modules.whatsapp_adapters import send_whatsapp_typing_indicator
        await start_training_mode(
            user_id=user_whatsapp_id,
            user_data=config.user_data_whatsapp[user_whatsapp_id],
            send_message_func=_adapter_send,
            send_action_func=send_whatsapp_typing_indicator
        )
    else:
        await adapter.send_text_message(user_whatsapp_id, "ليس لديك صلاحية لتفعيل وضع التدريب.")


async def exit_training_mode_whatsapp(user_whatsapp_id: str):
    """Adapts exit_training_mode for WhatsApp."""
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)

    async def _adapter_send(to: str, msg: str = None, img: str = None, aud: str = None):
        if msg:
            return await adapter.send_text_message(to, msg)
        elif img:
            return await adapter.send_image_message(to, img)
        elif aud:
            return await adapter.send_audio_message(to, aud)
        return False

    if user_whatsapp_id == TRAINER_WHATSAPP_NUMBER:
        if user_whatsapp_id not in config.user_data_whatsapp:
            config.user_data_whatsapp[user_whatsapp_id] = {'user_preferred_lang': 'ar', 'initial_user_query_to_process': None, 'awaiting_human_handover_confirmation': False, 'current_conversation_id': None}

        from modules.whatsapp_adapters import send_whatsapp_typing_indicator
        await exit_training_mode(
            user_id=user_whatsapp_id,
            user_data=config.user_data_whatsapp[user_whatsapp_id],
            send_message_func=_adapter_send,
            send_action_func=send_whatsapp_typing_indicator
        )
    else:
        await adapter.send_text_message(user_whatsapp_id, "ليس لديك صلاحية لإلغاء تفعيل وضع التدريب.")


async def generate_daily_report_command_whatsapp(user_whatsapp_id: str):
    """Adapts generate_daily_report_command for WhatsApp."""
    current_provider = WhatsAppFactory.get_current_provider()
    adapter = WhatsAppFactory.get_adapter(current_provider)

    async def _adapter_send(to: str, msg: str = None, img: str = None, aud: str = None):
        if msg:
            return await adapter.send_text_message(to, msg)
        elif img:
            return await adapter.send_image_message(to, img)
        elif aud:
            return await adapter.send_audio_message(to, aud)
        return False

    if user_whatsapp_id == TRAINER_WHATSAPP_NUMBER:
        await adapter.send_text_message(user_whatsapp_id, "جارٍ توليد التقرير اليومي... 📊")

        try:
            await generate_daily_report_command(
                user_id=user_whatsapp_id,
                send_message_func=_adapter_send
            )
        except Exception as e:
            print(f"ERROR generating daily report for {user_whatsapp_id}: {e}")
            await adapter.send_text_message(user_whatsapp_id, f"حدث خطأ أثناء توليد التقرير: {str(e)}")
    else:
        await adapter.send_text_message(user_whatsapp_id, "ليس لديك صلاحية لطلب التقرير اليومي.")


async def send_whatsapp_typing_indicator(user_whatsapp_id: str):
    """Sends a typing indicator to WhatsApp."""
    print(f"DEBUG: WhatsApp typing indicator for {user_whatsapp_id} (simulated).\n")
