"""MontyMobile webhook parse helpers/mixin (LOC split)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast


def _synthetic_wa_message_id(message: dict[str, Any]) -> str:
    """Stable id when Meta/WhatsApp omits message.id (avoids collapsing all to 'montymobile_')."""
    basis = json.dumps(message, sort_keys=True, default=str)
    return "synth_" + hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()[:48]


def _stable_id_when_provider_omits_message_id(webhook_data: dict[str, Any]) -> str:
    """
    Generic MontyMobile / simple-test parsers used time.time() when id was missing — every duplicate
    webhook got a different message_id and bypassed Firestore + in-memory dedupe. Hash the payload
    minus volatile keys so identical retries dedupe correctly.
    """
    drop = {"timestamp", "received_at", "ts", "time"}
    pruned = {k: v for k, v in webhook_data.items() if k not in drop}
    basis = json.dumps(pruned, sort_keys=True, default=str)
    return "synth_" + hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()[:48]


class MontyMobileAdapterParseMixin:
    """Parse inbound MontyMobile / Meta / legacy Qiscus webhook payloads."""

    def parse_webhook_message(self, webhook_data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Parse incoming MontyMobile webhook message to standard format

        MontyMobile webhook format (needs to be confirmed):
        Expected similar structure to Qiscus but with MontyMobile specifics
        """
        try:
            import os

            if os.getenv("DEBUG_MONTYMOBILE", "false").lower() == "true":
                print(f"🔔 MontyMobile webhook: object={webhook_data.get('object', 'N/A')}")

            # MontyMobile sends Meta/WhatsApp Cloud API format
            # Try Meta format if we have entry+changes structure (object may vary)
            if "entry" in webhook_data and webhook_data.get("entry"):
                entry0 = webhook_data["entry"][0] if isinstance(webhook_data["entry"], list) else {}
                changes = entry0.get("changes", []) if isinstance(entry0, dict) else []
                if changes and len(changes) > 0 and isinstance(changes[0], dict):
                    val = changes[0].get("value", {})
                    if isinstance(val, dict):
                        # Delivered/read/sent receipts — not inbound user text (avoid "Unknown format" noise)
                        msgs = val.get("messages") or []
                        if val.get("statuses") and not msgs:
                            if os.getenv("DEBUG_WEBHOOK_STATUSES", "false").lower() == "true":
                                print("ℹ️ MontyMobile webhook: status-only (delivery/read); ignored")
                            return None
                    if isinstance(val, dict) and ("messages" in val or "contacts" in val):
                        print("✅ Detected Meta/WhatsApp format (entry+changes)")
                        result = self._parse_meta_format(webhook_data)
                        if result:
                            return result

            # Fallback: Old Qiscus format (for backward compatibility)
            if webhook_data.get("type") in ["post_comment_mobile", "post_comment_rest"]:
                print("✅ Detected old Qiscus format")
                return self._parse_qiscus_format(webhook_data)

            # Fallback: Generic MontyMobile format
            elif "from" in webhook_data and "message" in webhook_data:
                print("✅ Detected generic MontyMobile format")
                return self._parse_montymobile_format(webhook_data)

            # Simple test format: {from, to, text, type, messageId, timestamp}
            elif "from" in webhook_data and "text" in webhook_data and "type" in webhook_data:
                print("✅ Detected simple test webhook format")
                return self._parse_simple_format(webhook_data)

            print("❌ ERROR: Unknown webhook format")
            print(f"Available keys: {list(webhook_data.keys())}")
            return None

        except Exception as e:
            print(f"ERROR parsing MontyMobile webhook: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _parse_qiscus_format(self, webhook_data: dict[str, Any]) -> dict[str, Any] | None:
        """Parse old Qiscus format for backward compatibility"""
        try:
            payload = webhook_data.get("payload", {})

            from_user = payload.get("from", {})
            user_id = str(from_user.get("id", ""))
            user_email = from_user.get("email", "")
            user_name = from_user.get("name", user_email)

            room = payload.get("room", {})
            room_id = str(room.get("id", ""))
            _room_name = room.get("name", "")

            phone_number = self._extract_phone_from_qiscus_room(room, from_user)

            if not room_id:
                print("ERROR: No room_id found in webhook!")
                return None

            # Store mapping
            self.room_mapping[room_id] = phone_number or ""
            if phone_number:
                self.room_mapping[phone_number] = room_id

            message = payload.get("message", {})
            message_type = message.get("type", "text")
            message_text = message.get("text", "")

            unique_id = message.get("unique_temp_id", message.get("id_str", message.get("id", str(hash(message_text)))))

            parsed_message = {
                "user_id": room_id,
                "user_name": user_name,
                "message_id": f"montymobile_{unique_id}",
                "timestamp": str(int(__import__("time").time())),
                "type": message_type,
                "content": self._extract_message_content(message),
                "room_id": room_id,
                "original_user_id": user_id,
                "phone_number": phone_number,
            }

            return parsed_message

        except Exception as e:
            print(f"ERROR parsing Qiscus format: {e}")
            return None

    def _parse_meta_format(self, webhook_data: dict[str, Any]) -> dict[str, Any] | None:
        """Parse Meta/WhatsApp Cloud API format (sent by MontyMobile)"""
        try:
            print("📥 Parsing Meta format webhook...")

            # Navigate through Meta webhook structure (with bounds checking)
            entry_list = webhook_data.get("entry", [])
            if not entry_list:
                print("❌ No entry in webhook")
                return None
            entry = entry_list[0]
            changes_list = entry.get("changes", [])
            if not changes_list:
                print("❌ No changes in webhook entry")
                return None
            changes = changes_list[0]
            value = changes.get("value", {})

            # CRITICAL FIX: Check if this is a status update (not a message)
            # Status updates should be ignored to prevent processing bot's own messages
            if "statuses" in value:
                print("⚠️ Ignoring status update webhook (not a user message)")
                return None

            # Extract message first (message.from is the canonical sender)
            messages = value.get("messages", [])
            if not messages:
                print("❌ No messages in webhook")
                return None

            message = messages[0]
            message_id = (message.get("id") or "").strip()
            if not message_id:
                message_id = _synthetic_wa_message_id(message)
                print(f"⚠️ Meta webhook missing message.id — using synthetic id {message_id[:24]}...")
            message_from = str(message.get("from", "")).strip()
            message_type = message.get("type", "text")
            timestamp = message.get("timestamp", str(int(__import__("time").time())))

            # CRITICAL: Use message.from as PRIMARY for user_id – it's the actual sender.
            # contacts[0].wa_id can be wrong (e.g. MontyMobile sending same contact for all).
            contacts = value.get("contacts", [])
            contact = contacts[0] if contacts else {}
            contact_wa_id = contact.get("wa_id", "")
            phone_number = message_from if message_from else contact_wa_id
            user_name = contact.get("profile", {}).get("name", "") or phone_number

            if message_from and contact_wa_id and message_from != contact_wa_id:
                print(
                    f"⚠️ WARNING: message.from ({message_from}) != contact.wa_id ({contact_wa_id}) – using message.from as sender"
                )

            # CRITICAL FIX: Check if message is from our bot number
            if message_from and (message_from == self.source_number or message_from == f"+{self.source_number}"):
                print(f"⚠️ Ignoring message from our own bot number: {message_from}")
                return None

            if not phone_number:
                print("❌ No sender (message.from or contact.wa_id)")
                return None

            # Add + prefix to phone if not present
            if phone_number and not phone_number.startswith("+"):
                phone_number = f"+{phone_number}"

            print(f"✅ Extracted: phone={phone_number}, name={user_name}, type={message_type}, from={message_from}")

            # Extract content based on type
            content = {}
            if message_type == "text":
                content = {"text": message.get("text", {}).get("body", "")}
            elif message_type == "image":
                content = {"image_id": message.get("image", {}).get("id", "")}
            elif message_type == "audio":
                audio_obj = message.get("audio", {}) or {}
                audio_id = audio_obj.get("id") or audio_obj.get("link") or audio_obj.get("url") or ""
                content = {"audio_id": audio_id}
            elif message_type == "video":
                content = {"video_id": message.get("video", {}).get("id", "")}
            elif message_type == "document":
                content = {"document_id": message.get("document", {}).get("id", "")}
            elif message_type == "interactive":
                inter = message.get("interactive") or {}
                if inter.get("type") == "button_reply":
                    br = inter.get("button_reply") or {}
                    synthetic = str(br.get("id") or br.get("title") or "").strip()
                elif inter.get("type") == "list_reply":
                    lr = inter.get("list_reply") or {}
                    synthetic = str(lr.get("id") or lr.get("title") or "").strip()
                else:
                    synthetic = ""
                content = {"text": synthetic}
                message_type = "text"
            else:
                content = {"raw": message}

            parsed_message = {
                "user_id": phone_number,  # Use phone as user_id
                "user_name": user_name,
                "message_id": f"montymobile_{message_id}",
                "timestamp": timestamp,
                "type": message_type,
                "content": content,
                "phone_number": phone_number,
            }

            print("✅ Successfully parsed Meta format webhook")
            return parsed_message

        except Exception as e:
            print(f"❌ ERROR parsing Meta format: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _parse_montymobile_format(self, webhook_data: dict[str, Any]) -> dict[str, Any] | None:
        """Parse generic MontyMobile format (fallback)"""
        try:
            from_data = webhook_data.get("from", {})
            phone_number = from_data.get("phone", "")
            user_name = from_data.get("name", phone_number)

            message = webhook_data.get("message", {})
            message_type = message.get("type", "text")
            raw_mid = message.get("id")
            if raw_mid is None or (isinstance(raw_mid, str) and not raw_mid.strip()):
                message_id = _stable_id_when_provider_omits_message_id(webhook_data)
                print(f"⚠️ MontyMobile generic format missing message.id — stable synthetic {message_id[:24]}...")
            else:
                message_id = str(raw_mid).strip()

            parsed_message = {
                "user_id": phone_number,
                "user_name": user_name,
                "message_id": f"montymobile_{message_id}",
                "timestamp": str(int(__import__("time").time())),
                "type": message_type,
                "content": self._extract_message_content(message),
                "phone_number": phone_number,
            }

            return parsed_message

        except Exception as e:
            print(f"ERROR parsing MontyMobile format: {e}")
            return None

    def _parse_simple_format(self, webhook_data: dict[str, Any]) -> dict[str, Any] | None:
        """Parse simple test webhook format: {from, to, text, type, messageId, timestamp}"""
        try:
            phone_number = webhook_data.get("from", "")
            message_type = webhook_data.get("type", "text")
            raw_mid = webhook_data.get("messageId")
            if raw_mid is None or (isinstance(raw_mid, str) and not str(raw_mid).strip()):
                message_id = _stable_id_when_provider_omits_message_id(webhook_data)
                print(f"⚠️ Simple webhook format missing messageId — stable synthetic {message_id[:24]}...")
            else:
                message_id = str(raw_mid).strip()
            timestamp = webhook_data.get("timestamp", int(__import__("time").time() * 1000))

            # Extract content based on type (must be dict with *_id for webhook handler)
            content = {}
            if message_type == "text":
                text_data = webhook_data.get("text", {})
                body = text_data.get("body", "") if isinstance(text_data, dict) else str(text_data)
                content = {"text": body}
            elif message_type == "image":
                image_data = webhook_data.get("image", {})
                img_id = image_data.get("id") or image_data.get("link", "") if isinstance(image_data, dict) else ""
                content = {"image_id": img_id}
            elif message_type == "audio":
                audio_data = webhook_data.get("audio", {})
                audio_id = (
                    (audio_data.get("id") or audio_data.get("link") or audio_data.get("url", ""))
                    if isinstance(audio_data, dict)
                    else ""
                )
                content = {"audio_id": audio_id}

            parsed_message = {
                "user_id": phone_number,
                "user_name": phone_number,  # Use phone as name for test messages
                "message_id": message_id,
                "timestamp": str(timestamp),
                "type": message_type,
                "content": content,
                "phone_number": phone_number,
            }

            print(f"✅ Parsed simple format: {parsed_message}")
            return parsed_message

        except Exception as e:
            print(f"ERROR parsing simple format: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _extract_phone_from_qiscus_room(self, room: dict[str, Any], from_user: dict[str, Any]) -> str | None:
        """Extract phone number from room information (same as Qiscus adapter)"""
        try:
            import re

            room_name = room.get("name", "")
            print(f"DEBUG: Checking room name for phone: {room_name}")

            phone_patterns = [r"\+(\d{1,4})\s*(\d{8,12})", r"(\d{1,4})\s*(\d{8,12})", r"\+(\d{10,15})", r"(\d{10,15})"]

            for pattern in phone_patterns:
                match = re.search(pattern, room_name)
                if match:
                    if len(match.groups()) == 2:
                        country_code = match.group(1)
                        number = match.group(2)
                        phone = f"+{country_code}{number}"
                    else:
                        phone = match.group(1)
                        if not phone.startswith("+"):
                            phone = f"+{phone}"

                    print(f"DEBUG: Found phone in room name: {phone}")
                    return phone

            user_email = from_user.get("email", "")
            print(f"DEBUG: Checking user email for phone: {user_email}")

            if user_email.isdigit() and len(user_email) >= 8:
                phone = f"+{user_email}"
                print(f"DEBUG: Found phone as user email (direct): {phone}")
                return phone

            if "@wa.qiscus.com" in user_email or "@whatsapp" in user_email:
                phone_part = user_email.split("@")[0]
                if phone_part.isdigit() and len(phone_part) >= 8:
                    phone = f"+{phone_part}"
                    print(f"DEBUG: Found phone in user email: {phone}")
                    return phone

            print("DEBUG: No phone number found in room information")
            return None

        except Exception as e:
            print(f"ERROR extracting phone: {e}")
            return None

    def _extract_message_content(self, message: dict[str, Any]) -> dict[str, Any]:
        """Extract message content from message format"""
        msg_type = message.get("type", "text")

        if msg_type == "text":
            return {"text": message.get("text", "")}

        elif msg_type == "file_attachment":
            payload = message.get("payload", {})
            url = payload.get("url", "")
            caption = payload.get("caption", "")
            message_text = message.get("text", "").lower()

            if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]):
                return {"image_id": url, "caption": caption}

            is_audio = (
                any(ext in url.lower() for ext in [".mp3", ".wav", ".ogg", ".m4a", ".opus", ".oga", ".aac", ".flac"])
                or "voice" in caption.lower()
                or "audio" in caption.lower()
                or "voice" in message_text
                or "audio" in message_text
                or "ptt" in url.lower()
            )

            if is_audio:
                return {"audio_id": url}

            if any(ext in url.lower() for ext in [".mp4", ".avi", ".mov", ".mkv", ".webm"]):
                return {"video_id": url, "caption": caption}

            return {"document_id": url, "filename": caption or "document"}

        elif msg_type == "audio":
            audio_obj = message.get("audio", {})
            if isinstance(audio_obj, dict):
                audio_id = audio_obj.get("id") or audio_obj.get("link") or audio_obj.get("url") or ""
            else:
                audio_id = ""
            return {"audio_id": audio_id} if audio_id else {"raw": message}

        elif msg_type == "location":
            payload = message.get("payload", {})
            return {
                "latitude": payload.get("latitude"),
                "longitude": payload.get("longitude"),
                "name": payload.get("name", ""),
                "address": payload.get("address", ""),
            }

        else:
            return {"raw": message}

    def _get_phone_from_room_id(self, room_id: str) -> str:
        """Convert room_id to phone number if needed"""
        # If room_id looks like a phone number, use it directly
        if room_id.startswith("+") or (
            room_id.replace("+", "").replace("-", "").replace(" ", "").isdigit() and len(room_id) >= 8
        ):
            return room_id

        # Check if we have a mapping
        if room_id in self.room_mapping:
            phone = self.room_mapping[room_id]
            if phone:
                return cast(str, phone)

        # Fallback: return room_id as-is
        print(f"WARNING: No phone mapping found for room_id {room_id}, using as-is")
        return room_id

