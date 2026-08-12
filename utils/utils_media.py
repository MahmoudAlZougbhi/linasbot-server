"""Voice transcription, media conversion/upload, dashboard metrics."""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any

import config
from services.live_chat_contracts import (
    utc_now,
)
from utils.utils_firestore import get_firestore_db
from utils.utils_livechat_hooks import _invalidate_live_chat_cache

_log = logging.getLogger(__name__)


async def update_voice_message_with_transcription(
    user_id: str, conversation_id: str, audio_url: str, transcribed_text: str, phone_number: str | None = None
) -> Any:
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
        phone_number:  phone number for user lookup
    """
    if hasattr(config, "TESTING_MODE") and config.TESTING_MODE:
        print("🧪 TESTING MODE: Skipping Firebase update for voice message")
        return

    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Skipping voice message update.")
        return

    app_id_for_firestore = "linas-ai-bot-backend"

    try:
        # Get the conversation document
        doc_ref = (
            db.collection("artifacts")
            .document(app_id_for_firestore)
            .collection("users")
            .document(user_id)
            .collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
            .document(conversation_id)
        )
        doc_snap = doc_ref.get()

        if not doc_snap.exists:
            print(f"⚠️ Conversation {conversation_id} not found for update")
            return

        doc_data = doc_snap.to_dict()
        current_messages = doc_data.get("messages", [])

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
        doc_ref.update({"messages": current_messages, "last_updated": utc_now()})
        _invalidate_live_chat_cache()

        print(f"✅ Updated voice message in conversation {conversation_id} with transcription")
        print(f"   Text: {transcribed_text[:50]}...")
        print(f"   Audio URL: {audio_url}")

    except Exception as e:
        print(f"❌ ERROR updating voice message in Firestore for user {user_id}: {e}")
        import traceback

        traceback.print_exc()

def convert_webm_to_opus(base64_webm: str) -> tuple[str, str | None]:
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
        import time

        from pydub import AudioSegment

        print("🔄 Converting WebM audio to Opus format...")

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
            parameters=["-vbr", "on", "-compression_level", "10"],
        )
        ogg_bytes = ogg_buffer.getvalue()
        print(f"   ✅ Converted to OGG/Opus: {len(ogg_bytes)} bytes")

        # Encode back to base64
        base64_ogg = base64.b64encode(ogg_bytes).decode("utf-8")

        # Create new filename with .ogg extension (WhatsApp compatible)
        timestamp = int(time.time())
        file_name = f"voice_{timestamp}.ogg"

        print(f"   ✅ Conversion complete! New file: {file_name}")
        return base64_ogg, file_name

    except Exception as e:
        print(f"❌ ERROR converting WebM to Opus: {e}")
        import traceback

        traceback.print_exc()
        print("   ⚠️ Falling back to original WebM format...")
        # Fall back to original if conversion fails
        return base64_webm, None

async def upload_base64_to_firebase_storage(
    base64_data: str, file_name: str, file_type: str = "audio/webm"
) -> str | None:
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
        with open(local_path, "wb") as f:
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
            encoded_path = quote(storage_path, safe="")
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

async def update_dashboard_metric_in_firestore(user_id: str, metric_name: str, increment_by: int = 1) -> None:
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
    metrics_doc_ref = (
        db.collection("artifacts")
        .document(app_id_for_firestore)
        .collection("users")
        .document(user_id)
        .collection(config.FIRESTORE_METRICS_COLLECTION)
        .document("summary")
    )

    try:
        # Get the current metrics document
        doc_snap = metrics_doc_ref.get()  # Firebase Admin SDK get() is synchronous

        if doc_snap.exists:
            current_metrics = doc_snap.to_dict()
            current_value = current_metrics.get(metric_name, 0)
            metrics_doc_ref.update({metric_name: current_value + increment_by})
            print(
                f"✅ Updated metric '{metric_name}' for user {user_id} by {increment_by}. New value: {current_value + increment_by}"
            )
        else:
            # If document doesn't exist, create it with the initial value
            metrics_doc_ref.set({metric_name: increment_by})
            print(f"✅ Created metric '{metric_name}' for user {user_id} with initial value {increment_by}.")

    except Exception as e:
        print(f"❌ ERROR updating dashboard metric '{metric_name}' in Firestore for user {user_id}: {e}")
        import traceback

        traceback.print_exc()
