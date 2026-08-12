"""Qiscus webhook parse mixin (LOC split)."""

from __future__ import annotations

import json
from typing import Any


class QiscusAdapterParseMixin:
    """Parse inbound Qiscus webhook payloads."""

    def parse_webhook_message(self, webhook_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Parse incoming Qiscus webhook message to standard format

        Qiscus webhook format:
        {
            "type": "post_comment_mobile",
            "payload": {
                "from": {"id": 1, "email": "user@example.com", "name": "User"},
                "room": {
                    "id": 1,
                    "topic_id": 1,
                    "type": "group",
                    "name": "WhatsApp Room - +96170123456",
                    "options": {
                        "source": "wa",
                        "channel_details": {"channel_id": 1, "name": "WhatsApp Channel"}
                    },
                    "participants": [...]
                },
                "message": {"type": "text", "text": "message", "payload": {}}
            }
        }
        """
        try:
            print(f"DEBUG: Parsing Qiscus webhook: {json.dumps(webhook_data, indent=2)}")

            # Check if this is a Qiscus webhook
            if webhook_data.get("type") in ["post_comment_mobile", "post_comment_rest"]:
                payload = webhook_data.get("payload", {})

                # Extract user information
                from_user = payload.get("from", {})
                user_id = str(from_user.get("id", ""))
                user_email = from_user.get("email", "")
                user_name = from_user.get("name", user_email)

                # Extract room information - THIS IS CRITICAL
                room = payload.get("room", {})
                room_id = str(room.get("id", ""))
                room_name = room.get("name", "")
                room_options = room.get("options", {})

                print(f"DEBUG: Extracted room_id: {room_id}, room_name: {room_name}")
                print(f"DEBUG: Room options: {room_options}")

                # Extract phone number from room name or participants
                phone_number = self._extract_phone_from_qiscus_room(room, from_user)
                print(f"🔍 DEBUG: Phone extraction result: ***{str(phone_number)[-4:] if phone_number else ''}")
                if not phone_number:
                    print("❌ CRITICAL: Phone extraction FAILED!")
                    print(f"❌ Room name: {room_name}")
                    print(f"❌ User email_len={len(str(user_email or ''))}")
                    print(f"❌ Room options: {room_options}")

                # Validate room_id exists
                if not room_id or room_id == "":
                    print("ERROR: No room_id found in Qiscus webhook!")
                    return None

                # Store room mapping for future use
                self.room_mapping[user_id] = room_id
                if phone_number:
                    self.room_mapping[phone_number] = room_id
                print(f"DEBUG: Stored room mapping - user_id: ...{str(user_id)[-4:]} -> room_id: {room_id}")
                if phone_number:
                    print(f"DEBUG: Stored phone mapping - phone: ***{str(phone_number)[-4:] if phone_number else ''} -> room_id={room_id}")

                # Extract message information
                message = payload.get("message", {})
                message_type = message.get("type", "text")
                message_text = message.get("text", "")
                _message_payload = message.get("payload", {})

                print(f"DEBUG: Message type: {message_type}, text_len={len(str(message_text or ''))}")

                # Generate unique message_id using unique_temp_id or message id
                # This prevents collision when message_text is empty (e.g., images with no caption)
                unique_id = message.get("unique_temp_id", "")
                if not unique_id or unique_id == "0":
                    # Fallback: use message id
                    unique_id = message.get("id_str", message.get("id", str(hash(message_text))))

                # Create standard format - IMPORTANT: Use room_id as user_id for responses
                parsed_message = {
                    "user_id": room_id,  # CRITICAL: Use room_id as user_id for sending responses
                    "user_name": user_name,
                    "message_id": f"qiscus_{unique_id}",  # Use unique_temp_id for true uniqueness
                    "timestamp": str(int(__import__("time").time())),
                    "type": message_type,
                    "content": self._extract_qiscus_message_content(message),
                    "room_id": room_id,  # Store room_id separately for reference
                    "original_user_id": user_id,  # Store original user_id for reference
                    "phone_number": phone_number,  # Store extracted phone number
                }

                print(
                    f"DEBUG: Created parsed message with room_id: {room_id}, phone: {phone_number}, message_id: {parsed_message['message_id']}"
                )
                return parsed_message

            print(f"DEBUG: Not a Qiscus webhook format: {webhook_data.get('type', 'unknown')}")
            return None

        except Exception as e:
            print(f"ERROR parsing Qiscus webhook: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _extract_phone_from_qiscus_room(self, room: dict[str, Any], from_user: dict[str, Any]) -> str | None:
        """
        Extract phone number from Qiscus room information

        Qiscus typically stores phone numbers in:
        1. Room name (e.g., "WhatsApp Room - +96170123456")
        2. User email (e.g., "96170123456@wa.qiscus.com")
        3. Participant information
        """
        try:
            # Method 1: Extract from room name
            room_name = room.get("name", "")
            print(f"DEBUG: Checking room name for phone: ***{str(room_name)[-4:] if room_name else ''}")

            # Look for phone patterns in room name
            import re

            phone_patterns = [
                r"\+(\d{1,4})\s*(\d{8,12})",  # +961 70123456 or +96170123456
                r"(\d{1,4})\s*(\d{8,12})",  # 961 70123456 or 96170123456
                r"\+(\d{10,15})",  # +96170123456
                r"(\d{10,15})",  # 96170123456
            ]

            for pattern in phone_patterns:
                match = re.search(pattern, room_name)
                if match:
                    if len(match.groups()) == 2:
                        # Country code + number
                        country_code = match.group(1)
                        number = match.group(2)
                        phone = f"+{country_code}{number}"
                    else:
                        # Full number
                        phone = match.group(1)
                        if not phone.startswith("+"):
                            phone = f"+{phone}"

                    print(f"DEBUG: Found phone in room name: ***{str(phone)[-4:] if phone else ''}")
                    return phone

            # Method 2: Extract from user email (common in WhatsApp integrations)
            user_email = from_user.get("email", "")
            print(f"DEBUG: Checking user email for phone: email_len={len(str(user_email or ''))}")

            # Check if email is just a phone number (like "96176466674")
            if user_email.isdigit() and len(user_email) >= 8:
                phone = f"+{user_email}"
                print(f"DEBUG: Found phone as user email (direct): ***{str(phone)[-4:] if phone else ''}")
                return phone

            if "@wa.qiscus.com" in user_email or "@whatsapp" in user_email:
                # Extract phone from email like "96170123456@wa.qiscus.com"
                phone_part = user_email.split("@")[0]
                if phone_part.isdigit() and len(phone_part) >= 8:
                    phone = f"+{phone_part}"
                    print(f"DEBUG: Found phone in user email: ***{str(phone)[-4:] if phone else ''}")
                    return phone

            # Method 3: Check participants for phone information
            participants = room.get("participants", [])
            for participant in participants:
                participant_email = participant.get("email", "")
                if "@wa.qiscus.com" in participant_email or "@whatsapp" in participant_email:
                    phone_part = participant_email.split("@")[0]
                    if phone_part.isdigit() and len(phone_part) >= 8:
                        phone = f"+{phone_part}"
                        print(f"DEBUG: Found phone in participant email: ***{str(phone)[-4:] if phone else ''}")
                        return phone

            # Method 4: Check room options for channel details
            room_options = room.get("options", {})

            # CRITICAL FIX: room_options might be a JSON string, not a dict
            if isinstance(room_options, str):
                try:
                    import json

                    room_options = json.loads(room_options)
                    print(f"DEBUG: Parsed room options from JSON string: {room_options}")
                except json.JSONDecodeError as e:
                    print(f"DEBUG: Failed to parse room options JSON: {e}")
                    room_options = {}

            channel_details = room_options.get("channel_details", {})
            if channel_details:
                print(f"DEBUG: Channel details: {channel_details}")

                # Check if phone is directly in channel_details
                if "phone" in channel_details:
                    phone = channel_details["phone"]
                    # Clean up the phone number
                    phone = phone.replace(" ", "").replace("-", "")
                    if not phone.startswith("+"):
                        phone = f"+{phone}"
                    print(f"DEBUG: Found phone directly in channel_details: ***{str(phone)[-4:] if phone else ''}")
                    return phone

                # Some Qiscus integrations store phone in channel details
                for _key, value in channel_details.items():
                    if isinstance(value, str) and any(char.isdigit() for char in value):
                        for pattern in phone_patterns:
                            match = re.search(pattern, value)
                            if match:
                                if len(match.groups()) == 2:
                                    country_code = match.group(1)
                                    number = match.group(2)
                                    phone = f"+{country_code}{number}"
                                else:
                                    phone = match.group(1)
                                    if not phone.startswith("+"):
                                        phone = f"+{phone}"

                                print(f"DEBUG: Found phone in channel details: ***{str(phone)[-4:] if phone else ''}")
                                return phone

            print("DEBUG: No phone number found in room information")
            return None

        except Exception as e:
            print(f"ERROR extracting phone from Qiscus room: {e}")
            return None

    def _extract_qiscus_message_content(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        Extract message content from Qiscus message format
        """
        msg_type = message.get("type", "text")

        if msg_type == "text":
            return {"text": message.get("text", "")}

        elif msg_type == "file_attachment":
            payload = message.get("payload", {})
            url = payload.get("url", "")
            caption = payload.get("caption", "")
            message_text = message.get("text", "").lower()

            print(f"DEBUG: file_attachment - url_len={len(str(url or ''))}, caption_len={len(str(caption or ''))}, text_len={len(str(message_text or ''))}")

            # Determine file type from URL, caption, or message text
            # Check for images
            if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]):
                return {
                    "image_id": url,  # Use URL as image_id
                    "caption": caption,
                }

            # Check for audio/voice - IMPROVED DETECTION
            # WhatsApp voice messages might have .opus, .ogg, .oga extensions
            # or might be indicated by caption/text containing "voice" or "audio"
            is_audio = (
                any(ext in url.lower() for ext in [".mp3", ".wav", ".ogg", ".m4a", ".opus", ".oga", ".aac", ".flac"])
                or "voice" in caption.lower()
                or "audio" in caption.lower()
                or "voice" in message_text
                or "audio" in message_text
                or "ptt" in url.lower()  # PTT = Push To Talk (voice message)
            )

            if is_audio:
                print("✅ Detected as AUDIO message")
                return {
                    "audio_id": url  # Use URL as audio_id
                }

            # Check for video
            if any(ext in url.lower() for ext in [".mp4", ".avi", ".mov", ".mkv", ".webm"]):
                return {
                    "video_id": url,  # Use URL as video_id
                    "caption": caption,
                }

            # Default to document
            print("⚠️ Treating as document (no specific type detected)")
            return {
                "document_id": url,  # Use URL as document_id
                "filename": caption or "document",
            }

        elif msg_type == "location":
            payload = message.get("payload", {})
            return {
                "latitude": payload.get("latitude"),
                "longitude": payload.get("longitude"),
                "name": payload.get("name", ""),
                "address": payload.get("address", ""),
            }

        else:
            # Return raw message for unknown types
            return {"raw": message}
