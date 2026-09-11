from __future__ import annotations

import base64
import io
import time
from typing import Any

import httpx  # NEW: for downloading image from URL

import config

# The training handlers will also need modification,
# so we'll pass required data directly or make them WhatsApp-aware later.
from handlers.training_handlers import handle_training_input
from services.analytics_events import analytics  # 📊 ANALYTICS
from services.photo_analysis_service import get_bot_photo_analysis_from_gpt
from utils.utils import (  # NEW: Import Firestore utilities
    notify_human_on_whatsapp,
    save_conversation_message_to_firestore,
    update_dashboard_metric_in_firestore,
)


def _photo_analysis_enabled_for_tenant(tenant_id: str) -> bool:
    """True when published CM AI Limits enable image analysis."""
    try:
        from services.cm.capability_gates import image_analysis_enabled

        return image_analysis_enabled(tenant_id)
    except Exception as exc:
        print(f"[photo_handlers] ai_limits lookup failed for {tenant_id}: {exc}")
    return False


async def handle_photo_message(
    user_id: str, user_name: str, image_url: str, user_data: dict, send_message_func: Any, send_action_func: Any
) -> Any:
    """
    Handles photo messages for WhatsApp users.
    Downloads the image, sends it for analysis, and replies with the result.
    """
    config.user_names[user_id] = user_name  # Ensure name is updated

    # Wave 3: photo analysis is an optional CM capability (default off for new tenants).
    tenant_id = str(user_data.get("tenant_id") or "").strip()
    if not tenant_id:
        print("ERROR: photo handler refused — tenant_id required")
        return
    from services.customer_ai.flags import customer_brain_enabled

    if customer_brain_enabled():
        from handlers.text_handlers_respond import _process_and_respond
        from services.ai_reply_turn_runtime import run_reserved_customer_turn
        from services.customer_reply_v2.inbound_media import mark_inbound_attachment, store_inbound_image_base64

        if not user_data.get("_source_message_id") and image_url:
            user_data["_source_message_id"] = str(image_url)
        if str(image_url or "").startswith("data:"):
            store_inbound_image_base64(user_data, b64=image_url)
        elif image_url:
            from services.customer_reply_v2.inbound_media import store_inbound_image_from_url

            await store_inbound_image_from_url(user_data, image_url)
        else:
            mark_inbound_attachment(user_data, "image")
        from services.ai_reply_delivery import wrap_tracked_send

        tracked_send = wrap_tracked_send(send_message_func, user_data)
        await run_reserved_customer_turn(
            user_data,
            lambda: _process_and_respond(
                user_id,
                user_name,
                "[صورة]",
                user_data,
                tracked_send,
                send_action_func,
            ),
        )
        return
    if not _photo_analysis_enabled_for_tenant(tenant_id):
        await send_message_func(
            user_id,
            "Photo analysis is not enabled for this business. Please contact the team on WhatsApp if you need help.",
        )
        return

    if config.user_in_training_mode.get(user_id, False):
        print(
            f"[handle_photo_message] INFO: User ...{str(user_id)[-4:]} in training mode. Handing over to handle_training_input."
        )
        # Pass necessary data directly to handle_training_input for photo analysis in training mode
        await handle_training_input(
            user_id=user_id,
            user_name=user_name,
            image_url=image_url,  # Pass the image URL directly
            user_data=user_data,
            send_message_func=send_message_func,
            send_action_func=send_action_func,
        )
        return

    from services.ai_limits_enforcement import customer_image_limit_message, enforce_image_analysis_quota

    image_quota = enforce_image_analysis_quota(user_id=user_id, user_data=user_data, amount=1, consume=True)
    if not image_quota.allowed:
        await send_message_func(user_id, customer_image_limit_message(image_quota))
        return

    if (
        getattr(config, "ENFORCE_TOTAL_PHOTO_ANALYSIS_LIMIT", False)
        and config.user_photo_analysis_count[user_id] >= config.MAX_PHOTO_ANALYSIS_PER_USER
    ):
        await send_message_func(
            user_id,
            "عذراً، لقد وصلت إلى الحد الأقصى من تحليل الصور المسموح به في الوقت الحالي (10 صور). "
            "إذا كنت بحاجة إلى مساعدة إضافية، يرجى التواصل مع فريقنا مباشرة.",
        )
        notify_human_on_whatsapp(
            user_name,
            config.user_gender.get(user_id, "غير محدد"),
            f"حاول المستخدم {user_name} تجاوز حد تحليل الصور.",
            type_of_notification="تجاوز حد تحليل الصور",
        )
        return

    # ✅ FIXED: Save user's photo message to Firestore with type and image URL metadata
    current_conversation_id = user_data.get("current_conversation_id")
    source_message_id = user_data.pop("_source_message_id", None)
    image_metadata = {
        "type": "image",
        "image_url": image_url,  # Save the image URL for dashboard display
    }
    if source_message_id:
        image_metadata["source_message_id"] = source_message_id
    await save_conversation_message_to_firestore(
        user_id,
        "user",
        "[صورة]",  # Placeholder text
        current_conversation_id,
        user_name,
        user_data.get("phone_number"),
        metadata=image_metadata,
    )
    user_data["current_conversation_id"] = config.user_data_whatsapp[user_id][
        "current_conversation_id"
    ]  # Ensure it's updated locally

    await send_message_func(user_id, "عم شوف الصورة... ثواني و بكون جاهزة للرد! 📸")
    await send_action_func(user_id)  # Simulate typing indicator

    start_time = time.time()  # 📊 Track processing time

    try:
        # Check if image_url is already a base64 data URL
        if image_url.startswith("data:"):
            # Extract base64 data from data URL
            print("DEBUG: Image is already base64 data URL, extracting...")
            # Format: data:image/jpeg;base64,<base64_string>
            base64_image = image_url.split(",", 1)[1] if "," in image_url else image_url
            print(f"DEBUG: Extracted base64 string length: {len(base64_image)}")
        else:
            # Download the image from the provided URL
            print(f"DEBUG: Downloading image from URL: {image_url[:100]}...")
            async with httpx.AsyncClient() as client:
                photo_response = await client.get(image_url)
                photo_response.raise_for_status()  # Raise an exception for bad status codes

                photo_data_bytes = io.BytesIO(photo_response.content)
                photo_data_bytes.seek(0)

            base64_image = base64.b64encode(photo_data_bytes.read()).decode("utf-8")
            print(f"DEBUG: Encoded image to base64, length: {len(base64_image)}")

        bot_reply, analysis_data = await get_bot_photo_analysis_from_gpt(user_id, base64_image)

        # 📊 ANALYTICS: Log image message from user
        response_time_ms = (time.time() - start_time) * 1000

        from services.membership.provider_expense import record_pending_provider

        source_mid = str(user_data.get("_source_message_id") or user_data.get("provider_message_id") or "")
        record_pending_provider(
            event_id=f"vision:{tenant_id}:{source_mid or user_id[-8:]}",
            tenant_id=tenant_id,
            category="visual",
            feature="inbound_media",
            provider="openai",
            model="gpt-4o-mini",
            operation_id=source_mid or "photo",
        )
        analytics.log_message(
            source="user",
            msg_type="image",
            user_id=user_id,
            language=user_data.get("user_preferred_lang", "ar"),
            tokens=0,
            cost_usd=0.0,
            model="gpt-4o-mini",
            response_time_ms=response_time_ms,
            message_length=0,
        )
        analytics.log_message(
            source="bot",
            msg_type="text",
            user_id=user_id,
            language=user_data.get("user_preferred_lang", "ar"),
            tokens=0,
            cost_usd=0.0,
            model="gpt-4o-mini",
            response_time_ms=response_time_ms,
            message_length=len(bot_reply),
        )

        await send_message_func(user_id, bot_reply)
        # NEW: Save bot's reply to Firestore
        await save_conversation_message_to_firestore(
            user_id, "ai", bot_reply, user_data["current_conversation_id"], user_name, user_data.get("phone_number")
        )

        config.user_photo_analysis_count[user_id] += 1

        # NEW: Update dashboard metrics if it's a critical issue (e.g., burn report)
        if analysis_data.get("is_critical_issue"):
            await update_dashboard_metric_in_firestore(user_id, "burn_reports", 1)
            print(f"DEBUG: Updated 'burn_reports' metric for user ...{str(user_id)[-4:]}.")

    except Exception as e:
        print(f"❌ ERROR in handle_photo_message: {e}")
        error_reply = "🚫 آسفة، حدث خطأ أثناء معالجة صورتك. الرجاء المحاولة مرة أخرى."
        await send_message_func(user_id, error_reply)
        # NEW: Save error reply to Firestore
        await save_conversation_message_to_firestore(
            user_id, "ai", error_reply, user_data["current_conversation_id"], user_name, user_data.get("phone_number")
        )

        notify_human_on_whatsapp(
            user_name,
            config.user_gender.get(user_id, "غير محدد"),
            f"فشل معالجة صورة من: {user_name}. الخطأ: {e}",
            type_of_notification="خطأ معالجة صورة",
        )
