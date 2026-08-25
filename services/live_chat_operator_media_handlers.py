"""Operator voice/image upload, Firestore save, and channel delivery."""

from __future__ import annotations

from typing import Any

from services.live_chat_operator_social_delivery import (
    deliver_social_operator_media,
    is_social_live_chat_user,
)
from services.media_service import build_whatsapp_audio_delivery_url


async def send_operator_voice_message(
    *,
    message: str,
    user_id: str,
    canonical_user_id: str,
    conversation_id: str,
    operator_id: str,
    phone_number: str | None,
    tenant_id: str | None,
    adapter: Any,
    manual_meta: dict[str, Any],
) -> dict[str, Any]:
    from utils.utils import save_conversation_message_to_firestore

    print(f"🎙️ Operator {operator_id} recorded voice message for ...{str(user_id)[-4:]}")
    audio_data_to_upload: str | bytes = message
    upload_file_name = f"voice_{user_id}_{int(__import__('time').time())}.webm"
    upload_file_type = "audio/webm"

    try:
        from utils.utils import convert_webm_to_opus

        opus_data, opus_file_name = convert_webm_to_opus(message)
        if opus_file_name:
            audio_data_to_upload = opus_data
            upload_file_name = opus_file_name
            upload_file_type = "audio/ogg"
            print("✅ Voice converted to OGG/Opus")
    except Exception as e:
        print(f"⚠️ WebM to Opus conversion failed: {e}")

    storage_url = None
    try:
        import base64

        from utils.utils import upload_base64_to_firebase_storage

        upload_payload = (
            audio_data_to_upload
            if isinstance(audio_data_to_upload, str)
            else base64.b64encode(audio_data_to_upload).decode()
        )
        storage_url = await upload_base64_to_firebase_storage(
            base64_data=upload_payload, file_name=upload_file_name, file_type=upload_file_type
        )
        print(f"✅ Voice uploaded to Storage: {storage_url}")
    except Exception as e:
        print(f"⚠️ Failed to upload to Storage: {e}")
        storage_url = None

    await save_conversation_message_to_firestore(
        user_id=canonical_user_id,
        role="operator",
        text="[Voice Message from Operator]",
        conversation_id=conversation_id,
        phone_number=phone_number,
        metadata={
            "operator_id": operator_id,
            "handled_by": "human",
            "type": "voice",
            "audio_url": storage_url,
            "audio_mime_type": upload_file_type,
            "message_length": len(message),
        },
    )

    print(f"🎙️ Sending voice message to ...{str(user_id)[-4:]}...")
    try:
        if is_social_live_chat_user(user_id):
            if not storage_url and not audio_data_to_upload:
                return {"success": False, "error": "Voice upload failed", **manual_meta}
            delivery = await deliver_social_operator_media(
                tenant_id=tenant_id,
                user_id=user_id,
                media_bytes=audio_data_to_upload if isinstance(audio_data_to_upload, bytes) else None,
                payload=audio_data_to_upload if isinstance(audio_data_to_upload, str) else message,
                mime=upload_file_type,
                filename=upload_file_name,
            )
            if delivery and not delivery.get("success"):
                err = str(delivery.get("error") or "social_voice_delivery_failed")
                return {"success": False, "error": err, **manual_meta}
            return {
                "success": True,
                "message": "Voice message sent successfully",
                "storage_url": storage_url,
                "delivered": True,
                **manual_meta,
                **(delivery or {}),
            }

        if storage_url:
            whatsapp_audio_url = build_whatsapp_audio_delivery_url(storage_url)
            send_result = await adapter.send_audio_message(canonical_user_id, whatsapp_audio_url)
            if not send_result.get("success"):
                error_msg = send_result.get("error", "Unknown error")
                return {
                    "success": False,
                    "error": f"WhatsApp audio send failed: {error_msg}",
                    "storage_url": storage_url,
                    "whatsapp_audio_url": whatsapp_audio_url,
                }
        else:
            text_notification = "تم استلام رسالة صوتية من المشغل. يرجى فتح لوحة المعلومات لسماعها."
            await adapter.send_text_message(canonical_user_id, text_notification)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"success": False, "error": f"Failed to send voice: {str(e)}"}

    return {
        "success": True,
        "message": "Voice message sent successfully",
        "storage_url": storage_url,
        "whatsapp_audio_url": build_whatsapp_audio_delivery_url(storage_url) if storage_url else None,
        **manual_meta,
    }


async def send_operator_image_message(
    *,
    message: str,
    user_id: str,
    canonical_user_id: str,
    conversation_id: str,
    operator_id: str,
    phone_number: str | None,
    tenant_id: str | None,
    adapter: Any,
    manual_meta: dict[str, Any],
) -> dict[str, Any]:
    from utils.utils import save_conversation_message_to_firestore

    print(f"🖼️ Operator {operator_id} uploaded image for ...{str(user_id)[-4:]}")
    storage_url = None
    try:
        from utils.utils import upload_base64_to_firebase_storage

        storage_url = await upload_base64_to_firebase_storage(
            base64_data=message,
            file_name=f"image_{user_id}_{int(__import__('time').time())}.jpg",
            file_type="image/jpeg",
        )
        print(f"✅ Image uploaded to Storage: {storage_url}")
    except Exception as e:
        print(f"⚠️ Failed to upload to Storage: {e}")
        storage_url = None

    await save_conversation_message_to_firestore(
        user_id=canonical_user_id,
        role="operator",
        text="[Image Message from Operator]",
        conversation_id=conversation_id,
        phone_number=phone_number,
        metadata={
            "operator_id": operator_id,
            "handled_by": "human",
            "type": "image",
            "image_data": message,
            "image_url": storage_url,
            "message_length": len(message),
        },
    )

    print(f"🖼️ Sending image to ...{str(user_id)[-4:]}...")
    try:
        if is_social_live_chat_user(user_id):
            delivery = await deliver_social_operator_media(
                tenant_id=tenant_id,
                user_id=user_id,
                payload=message,
                mime="image/jpeg",
                filename=f"image_{user_id}_{int(__import__('time').time())}.jpg",
            )
            if delivery and not delivery.get("success"):
                err = str(delivery.get("error") or "social_image_delivery_failed")
                return {"success": False, "error": err, **manual_meta}
            return {
                "success": True,
                "message": "Image message sent successfully",
                "storage_url": storage_url,
                "delivered": True,
                **manual_meta,
                **(delivery or {}),
            }

        if storage_url:
            send_result = await adapter.send_image_message(canonical_user_id, storage_url, caption="صورة من المشغل")
            if isinstance(send_result, dict) and not send_result.get("success", True):
                err = send_result.get("error", "Unknown error")
                return {"success": False, "error": f"WhatsApp image send failed: {err}"}
        else:
            text_notification = "تم استلام صورة من المشغل. يرجى فتح لوحة المعلومات لعرضها."
            await adapter.send_text_message(canonical_user_id, text_notification)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"success": False, "error": f"Failed to send image: {str(e)}"}

    return {
        "success": True,
        "message": "Image message sent successfully",
        "storage_url": storage_url,
        **manual_meta,
    }
