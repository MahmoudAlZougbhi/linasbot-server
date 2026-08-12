"""Smart messaging send-test (session text) route (LOC split)."""

from __future__ import annotations

from typing import Any

from modules.core import app


@app.post("/api/smart-messaging/send-test")
async def send_test_message(request_data: dict[str, Any]) -> Any:
    """Send a test message to a phone number using template data (OLD METHOD - for backward compatibility)"""
    try:
        phone_number = request_data.get("phone_number", "").strip()
        message = request_data.get("message", "").strip()
        template_id = request_data.get("template_id", "")
        language = request_data.get("language", "ar")

        # Validate inputs
        if not phone_number:
            return {"success": False, "error": "Phone number is required"}

        if not message:
            return {"success": False, "error": "Message content is empty"}

        print(f"📤 Sending test message to phone: ***{str(phone_number)[-4:] if phone_number else ''}")
        print(f"   Template: {template_id}")
        print(f"   Language: {language}")
        print(f"   Message preview: {message[:100]}...")

        # Normalize and clean the phone number for lookup
        phone_clean = phone_number.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")

        # Generate variations for matching
        phone_without_country = phone_clean.lstrip("961")  # Remove Lebanon country code
        phone_with_plus = f"+{phone_clean}"

        print(f"🔍 Searching for phone: ***{str(phone_number)[-4:] if phone_number else ''}")
        print(f"   Cleaned_last4: ***{str(phone_clean)[-4:] if phone_clean else ''}")
        print(f"   Without_country_last4: ***{str(phone_without_country)[-4:] if phone_without_country else ''}")

        print(f"🔍 Searching for phone: ***{str(phone_number)[-4:] if phone_number else ''}")
        print(f"   Cleaned_last4: ***{str(phone_clean)[-4:] if phone_clean else ''}")

        # Generate multiple phone variations for matching (handles different formats)
        phone_without_country = phone_clean.lstrip("961")  # Remove Lebanon country code
        phone_with_plus = f"+{phone_clean}"
        phone_with_plus_country = f"+961{phone_without_country}"

        print("   Variations to try:")
        print(f"     - ***{str(phone_clean)[-4:] if phone_clean else ''}")
        print(f"     - ***{str(phone_without_country)[-4:] if phone_without_country else ''}")
        print(f"     - ***{str(phone_with_plus)[-4:] if phone_with_plus else ''}")
        print(f"     - ***{str(phone_with_plus_country)[-4:] if phone_with_plus_country else ''}")

        # For Qiscus: need to fetch the room_id from Firebase using the phone number
        try:
            import config
            from utils.utils import get_firestore_db

            # First, try to find the room_id from Firebase by searching through users
            db = get_firestore_db()
            if db:
                app_id = "linas-ai-bot-backend"
                users_collection = db.collection("artifacts").document(app_id).collection("users")

                # Search for user by phone number
                room_id = None
                found_match = False

                print("📂 Searching in Firebase for matching phone...")
                for user_doc in users_collection.stream():
                    user_id = user_doc.id
                    user_data = user_doc.to_dict() or {}

                    # Phone data is stored at root level, NOT in customer_info
                    stored_phone_full = user_data.get("phone_full", "")
                    stored_phone_clean = user_data.get("phone_clean", "")

                    # Log what we're checking
                    if stored_phone_full or stored_phone_clean:
                        print(f"   Checking user_id=...{str(user_id)[-4:]}:")
                        print(f"     phone_full_last4: ***{str(stored_phone_full)[-4:] if stored_phone_full else ''}")
                        print(
                            f"     phone_clean_last4: ***{str(stored_phone_clean)[-4:] if stored_phone_clean else ''}"
                        )

                    # Clean both for comparison
                    stored_phone_full_clean = (
                        stored_phone_full.replace("+", "")
                        .replace("-", "")
                        .replace(" ", "")
                        .replace("(", "")
                        .replace(")", "")
                    )
                    stored_phone_without_country = stored_phone_clean.lstrip("961") if stored_phone_clean else ""

                    # Try multiple matching strategies
                    match_pairs = [
                        (stored_phone_clean, phone_clean),
                        (stored_phone_clean, phone_without_country),
                        (stored_phone_full_clean, phone_clean),
                        (stored_phone_full_clean, phone_without_country),
                        (stored_phone_full, phone_number),
                        (stored_phone_without_country, phone_without_country),
                    ]

                    if any(stored == inputted for stored, inputted in match_pairs if stored and inputted):
                        room_id = user_id
                        found_match = True
                        print(f"     ✅ MATCH FOUND! room_id = {room_id}")
                        break

                if not found_match:
                    print("❌ Phone not found in Firebase. Checking config fallback...")
                    # Fall back to config lookup - config has room_id as keys
                    for user_id, user_data in config.user_data_whatsapp.items():
                        user_phone = user_data.get("phone_number", "")
                        if not user_phone:
                            continue

                        user_phone_clean = (
                            user_phone.replace("+", "")
                            .replace("-", "")
                            .replace(" ", "")
                            .replace("(", "")
                            .replace(")", "")
                        )
                        user_phone_without_country = user_phone_clean.lstrip("961")

                        print(f"   Checking config user_id=...{str(user_id)[-4:]}:")
                        print(f"     phone_last4: ***{str(user_phone)[-4:] if user_phone else ''}")
                        print(f"     cleaned_last4: ***{str(user_phone_clean)[-4:] if user_phone_clean else ''}")

                        # Try matching with multiple variations
                        config_match_pairs = [
                            (user_phone_clean, phone_clean),
                            (user_phone_clean, phone_without_country),
                            (user_phone, phone_number),
                            (user_phone_without_country, phone_without_country),
                        ]

                        if any(stored == inputted for stored, inputted in config_match_pairs if stored and inputted):
                            room_id = user_id
                            found_match = True
                            print(f"     ✅ MATCH FOUND in config! room_id = {room_id}")
                            break

                if not room_id:
                    return {
                        "success": False,
                        "error": f"Phone number {phone_number} not found. Make sure customer has an active conversation.",
                    }
            else:
                return {"success": False, "error": "Database connection failed"}

            # Now send the message using Qiscus adapter with the room_id
            from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

            adapter = WhatsAppFactory.get_adapter()
            result = await adapter.send_text_message(to_number=room_id, message=message)

            if result.get("dry_run"):
                print(
                    f"📋 [DRY-RUN] Test message would be sent to ***{str(phone_number)[-4:] if phone_number else ''} (room {room_id})"
                )
                return {
                    "success": True,
                    "message": f"Dry-run: message not sent (local/sandbox mode). Would send to {phone_number}.",
                    "phone_number": phone_number,
                    "room_id": room_id,
                    "dry_run": True,
                }
            if result.get("success"):
                print(
                    f"✅ Test message sent successfully to ***{str(phone_number)[-4:] if phone_number else ''} (room {room_id})"
                )

                # Save to conversation history for continuous context
                from utils.utils import save_conversation_message_to_firestore

                await save_conversation_message_to_firestore(
                    user_id=room_id,
                    role="ai",
                    text=message,
                    conversation_id=None,
                    user_name="Customer",
                    phone_number=phone_number,
                    metadata={"source": "smart_message", "type": template_id or "test_message"},
                )
                print(
                    f"💾 Saved test message to conversation history for ***{str(phone_number)[-4:] if phone_number else ''}"
                )

                return {
                    "success": True,
                    "message": f"Test message sent to {phone_number}",
                    "phone_number": phone_number,
                    "room_id": room_id,
                    "template_id": template_id,
                    "language": language,
                }
            else:
                error_msg = result.get("error", "Unknown error")
                print(
                    f"❌ Failed to send test message to ***{str(phone_number)[-4:] if phone_number else ''} - {error_msg}"
                )
                return {"success": False, "error": f"Failed to send message: {error_msg}"}

        except Exception as lookup_error:
            print(f"❌ Error looking up room or sending message: {lookup_error}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": f"Error: {str(lookup_error)}"}

    except Exception as e:
        print(f"❌ Error sending test message: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": f"Failed to send test message: {str(e)}"}
