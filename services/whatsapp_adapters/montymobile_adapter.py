"""
MontyMobile WhatsApp Adapter
New Qiscus API endpoint using MontyMobile infrastructure
"""
import hashlib
import json
import time
from typing import Dict, Any, Optional
from .base_adapter import WhatsAppAdapter


def _synthetic_wa_message_id(message: Dict[str, Any]) -> str:
    """Stable id when Meta/WhatsApp omits message.id (avoids collapsing all to 'montymobile_')."""
    basis = json.dumps(message, sort_keys=True, default=str)
    return "synth_" + hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()[:48]


def _stable_id_when_provider_omits_message_id(webhook_data: Dict[str, Any]) -> str:
    """
    Generic MontyMobile / simple-test parsers used time.time() when id was missing — every duplicate
    webhook got a different message_id and bypassed Firestore + in-memory dedupe. Hash the payload
    minus volatile keys so identical retries dedupe correctly.
    """
    drop = {"timestamp", "received_at", "ts", "time"}
    pruned = {k: v for k, v in webhook_data.items() if k not in drop}
    basis = json.dumps(pruned, sort_keys=True, default=str)
    return "synth_" + hashlib.sha256(basis.encode("utf-8", errors="replace")).hexdigest()[:48]

class MontyMobileAdapter(WhatsAppAdapter):
    """MontyMobile WhatsApp API adapter (New Qiscus endpoint)"""
    
    def __init__(self, api_token: str, tenant_id: str, api_id: str, source_number: str, **kwargs):
        """
        Initialize the MontyMobile adapter
        
        Args:
            api_token: API key for authentication
            tenant_id: Tenant UUID for authentication
            api_id: API ID for the WhatsApp channel
            source_number: Source WhatsApp number (e.g., "96178974402")
            **kwargs: Additional configuration
        """
        super().__init__(api_token, tenant_id)  # Use tenant_id as phone_number_id equivalent
        
        # MontyMobile API configuration - NEW WHATSAPP NOTIFICATION ENDPOINT
        self.base_url = 'https://whatsapp-notification.montymobile.com'
        self.tenant_id = tenant_id
        self.api_id = api_id  # Keep for backward compatibility but not used in new endpoint
        self.source_number = source_number
        
        # MontyMobile authentication headers
        self.headers = {
            "Content-Type": "application/json",
            "Tenant": tenant_id,
            "api-key": api_token
        }
        
        # Store room mapping (user_id -> phone_number)
        self.room_mapping = {}
        
        print(f"✅ MontyMobile adapter initialized")
        print(f"   Base URL: {self.base_url}")
        print(f"   Tenant: {tenant_id}")
        print(f"   API ID: {api_id}")
        print(f"   Source: {source_number}")
    
    async def send_text_message(self, to_number: str, message: str) -> Dict[str, Any]:
        """
        Send a text message via MontyMobile
        
        Args:
            to_number: Destination phone number (can be room_id or phone)
            message: Text message to send
        """
        phone_number = self._get_phone_from_room_id(to_number)

        # NEW ENDPOINT - Updated from testing
        url = f"{self.base_url}/api/v2/WhatsappApi/send-session"

        # NEW PAYLOAD FORMAT - No apiId required
        payload = {
            "to": phone_number,
            "type": "TEXT",
            "source": self.source_number,
            "text": {
                "body": message
            }
        }

        try:
            import os
            if os.getenv("DEBUG_MONTYMOBILE", "false").lower() == "true":
                print(f"🔄 MONTYMOBILE: Sending to {phone_number[:6]}***")

            t0 = time.time()
            response = await self.client.post(url, headers=self.headers, json=payload)
            elapsed_ms = (time.time() - t0) * 1000

            response_text = response.text

            # Parse response
            try:
                result = response.json()

                # Check if successful based on MontyMobile response format
                if response.status_code == 200 and result.get("success"):
                    message_id = result.get("data", {}).get("messageId", "unknown")
                    print(f"✅ SUCCESS: Message sent to {phone_number}")
                    print(f"✅ Message ID: {message_id}")
                    return {"success": True, "data": result, "message_id": message_id}
                else:
                    error_msg = result.get("message", "Unknown error")
                    print(f"❌ FAILED: {error_msg}")
                    return {"success": False, "error": error_msg, "response": result}

            except json.JSONDecodeError:
                print(f"⚠️  Non-JSON response")
                if response.status_code == 200:
                    print(f"✅ Assuming success (HTTP 200)")
                    return {"success": True, "message": "Message sent"}
                else:
                    print(f"❌ Failed with status {response.status_code}")
                    return {"success": False, "error": f"HTTP {response.status_code}: {response_text}"}

        except Exception as e:
            print(f"\n{'='*80}")
            print(f"❌ EXCEPTION sending MontyMobile message")
            print(f"{'='*80}")
            print(f"❌ Error: {e}")
            print(f"❌ Error Type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            print(f"{'='*80}\n")
            return {"success": False, "error": str(e)}
    
    async def send_image_message(self, to_number: str, image_url: str, caption: str = None) -> Dict[str, Any]:
        """
        Send an image message via MontyMobile
        
        Args:
            to_number: Destination phone number (can be room_id or phone)
            image_url: URL of the image to send
            caption: Optional caption for the image
        """
        # NEW ENDPOINT
        url = f"{self.base_url}/api/v2/WhatsappApi/send-session"
        
        # Convert room_id to phone number if needed
        phone_number = self._get_phone_from_room_id(to_number)
        
        # NEW PAYLOAD FORMAT - No apiId
        payload = {
            "to": phone_number,
            "type": "IMAGE",
            "source": self.source_number,
            "image": {
                "link": image_url,
                "caption": caption or ""
            }
        }
        
        try:
            print(f"\n🔄 MONTYMOBILE: Sending image to {phone_number}")
            print(f"📤 Image URL: {image_url}")
            print(f"📤 Caption: {caption}")
            print(f"📤 Payload: {json.dumps(payload, indent=2)}")
            
            t0 = time.time()
            response = await self.client.post(url, headers=self.headers, json=payload)
            elapsed_ms = (time.time() - t0) * 1000

            print(f"⏱️  MONTYMOBILE IMAGE API TOOK: {elapsed_ms:.0f}ms")
            print(f"📥 Status: {response.status_code}")

            try:
                result = response.json()
                print(f"📥 Response: {json.dumps(result, indent=2, ensure_ascii=False)}")

                if response.status_code == 200 and result.get("success"):
                    print(f"✅ Image sent successfully")
                    return {"success": True, "data": result}
                else:
                    print(f"❌ Image send failed: {result.get('message')}")
                    return {"success": False, "error": result.get("message")}
            except json.JSONDecodeError:
                print(f"⚠️  Non-JSON response: {response.text[:200]}")
                if response.status_code == 200:
                    return {"success": True, "message": "Image sent"}
                else:
                    return {"success": False, "error": f"HTTP {response.status_code}"}
                    
        except Exception as e:
            print(f"❌ ERROR sending MontyMobile image: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def send_audio_message(self, to_number: str, audio_url: str, audio_base64: str = None) -> Dict[str, Any]:
        """
        Send an audio message via MontyMobile.
        Uses the audio URL (should be Firebase/Google CDN URL for reachability).

        Args:
            to_number: Destination phone number (can be room_id or phone)
            audio_url: URL of the audio file (Firebase Storage URL)
            audio_base64: Optional base64-encoded audio data (unused, kept for interface compat)
        """
        phone_number = self._get_phone_from_room_id(to_number)
        send_url = f"{self.base_url}/api/v2/WhatsappApi/send-session"

        try:
            print(f"\n🔄 MONTYMOBILE: Sending audio to {phone_number}")
            print(f"📤 Audio URL: {audio_url}")

            # Attempt 1: Send as DOCUMENT type with link (AUDIO type doesn't deliver)
            print(f"📤 Attempt 1: Sending as DOCUMENT with link...")
            doc_payload = {
                "to": phone_number,
                "type": "DOCUMENT",
                "source": self.source_number,
                "document": {
                    "link": audio_url,
                    "filename": "voice_message.ogg"
                }
            }
            t0 = time.time()
            response = await self.client.post(send_url, headers=self.headers, json=doc_payload)
            elapsed_ms = (time.time() - t0) * 1000
            print(f"⏱️  MONTYMOBILE AUDIO API TOOK: {elapsed_ms:.0f}ms")
            print(f"📥 Status: {response.status_code}")
            try:
                result = response.json()
                print(f"📥 Response: {json.dumps(result, indent=2, ensure_ascii=False)}")
                if response.status_code == 200 and result.get("success"):
                    print(f"✅ Audio sent as DOCUMENT type")
                    return {"success": True, "data": result}
            except json.JSONDecodeError:
                pass

            # Attempt 3: Fallback to text with link
            print(f"📤 Attempt 3: Fallback to text with link...")
            text_payload = {
                "to": phone_number,
                "type": "TEXT",
                "source": self.source_number,
                "text": {
                    "body": f"🎙️ Voice message: {audio_url}"
                }
            }
            text_response = await self.client.post(send_url, headers=self.headers, json=text_payload)
            print(f"📥 Text fallback status: {text_response.status_code}")

            if text_response.status_code == 200:
                return {"success": True, "message": "Audio sent as text link (fallback)", "method": "text_fallback"}
            else:
                return {"success": False, "error": "All audio send methods failed"}

        except Exception as e:
            print(f"❌ ERROR sending MontyMobile audio: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def send_document_message(self, to_number: str, document_url: str, filename: str = None) -> Dict[str, Any]:
        """
        Send a document message via MontyMobile
        
        Args:
            to_number: Destination phone number
            document_url: URL of the document to send
            filename: Optional filename for the document
        """
        # NEW ENDPOINT
        url = f"{self.base_url}/api/v2/WhatsappApi/send-session"
        
        phone_number = self._get_phone_from_room_id(to_number)
        
        # NEW PAYLOAD FORMAT - No apiId
        payload = {
            "to": phone_number,
            "type": "DOCUMENT",
            "source": self.source_number,
            "document": {
                "link": document_url,
                "filename": filename or "document"
            }
        }
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"MontyMobile document sent to {phone_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending MontyMobile document: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_button_message(self, to_number: str, text: str, buttons: list) -> Dict[str, Any]:
        """
        Send a button message via MontyMobile
        Note: Convert to text with numbered options
        
        Args:
            to_number: Destination phone number
            text: Button message text
            buttons: List of button objects
        """
        # Convert buttons to text format
        button_text = f"{text}\n\n"
        for i, button in enumerate(buttons, 1):
            button_text += f"{i}. {button.get('label', 'Option')}\n"
        
        return await self.send_text_message(to_number, button_text)
    
    async def download_media(self, media_id: str) -> bytes:
        """
        Download media file by ID
        """
        try:
            # media_id is actually the URL in MontyMobile
            response = await self.client.get(media_id)
            response.raise_for_status()
            return response.content
            
        except Exception as e:
            print(f"ERROR downloading MontyMobile media: {e}")
            raise
    
    async def set_webhook(self, webhook_url: str, events: list = None) -> Dict[str, Any]:
        """
        Set webhook URL for receiving messages
        Note: Webhook is configured in MontyMobile dashboard
        """
        print(f"MontyMobile webhook should be configured in dashboard: {webhook_url}")
        return {"success": True, "message": "Webhook configured in MontyMobile dashboard"}
    
    def parse_webhook_message(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
                        print(f"✅ Detected Meta/WhatsApp format (entry+changes)")
                        result = self._parse_meta_format(webhook_data)
                        if result:
                            return result
            
            # Fallback: Old Qiscus format (for backward compatibility)
            if webhook_data.get("type") in ["post_comment_mobile", "post_comment_rest"]:
                print(f"✅ Detected old Qiscus format")
                return self._parse_qiscus_format(webhook_data)
            
            # Fallback: Generic MontyMobile format
            elif "from" in webhook_data and "message" in webhook_data:
                print(f"✅ Detected generic MontyMobile format")
                return self._parse_montymobile_format(webhook_data)

            # Simple test format: {from, to, text, type, messageId, timestamp}
            elif "from" in webhook_data and "text" in webhook_data and "type" in webhook_data:
                print(f"✅ Detected simple test webhook format")
                return self._parse_simple_format(webhook_data)

            print(f"❌ ERROR: Unknown webhook format")
            print(f"Available keys: {list(webhook_data.keys())}")
            return None
            
        except Exception as e:
            print(f"ERROR parsing MontyMobile webhook: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _parse_qiscus_format(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse old Qiscus format for backward compatibility"""
        try:
            payload = webhook_data.get("payload", {})
            
            from_user = payload.get("from", {})
            user_id = str(from_user.get("id", ""))
            user_email = from_user.get("email", "")
            user_name = from_user.get("name", user_email)
            
            room = payload.get("room", {})
            room_id = str(room.get("id", ""))
            room_name = room.get("name", "")
            
            phone_number = self._extract_phone_from_qiscus_room(room, from_user)
            
            if not room_id:
                print(f"ERROR: No room_id found in webhook!")
                return None
            
            # Store mapping
            self.room_mapping[room_id] = phone_number
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
                "timestamp": str(int(__import__('time').time())),
                "type": message_type,
                "content": self._extract_message_content(message),
                "room_id": room_id,
                "original_user_id": user_id,
                "phone_number": phone_number
            }
            
            return parsed_message
            
        except Exception as e:
            print(f"ERROR parsing Qiscus format: {e}")
            return None
    
    def _parse_meta_format(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse Meta/WhatsApp Cloud API format (sent by MontyMobile)"""
        try:
            print(f"📥 Parsing Meta format webhook...")
            
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
                print(f"⚠️ Ignoring status update webhook (not a user message)")
                return None
            
            # Extract message first (message.from is the canonical sender)
            messages = value.get("messages", [])
            if not messages:
                print(f"❌ No messages in webhook")
                return None
                
            message = messages[0]
            message_id = (message.get("id") or "").strip()
            if not message_id:
                message_id = _synthetic_wa_message_id(message)
                print(f"⚠️ Meta webhook missing message.id — using synthetic id {message_id[:24]}...")
            message_from = str(message.get("from", "")).strip()
            message_type = message.get("type", "text")
            timestamp = message.get("timestamp", str(int(__import__('time').time())))
            
            # CRITICAL: Use message.from as PRIMARY for user_id – it's the actual sender.
            # contacts[0].wa_id can be wrong (e.g. MontyMobile sending same contact for all).
            contacts = value.get("contacts", [])
            contact = contacts[0] if contacts else {}
            contact_wa_id = contact.get("wa_id", "")
            phone_number = message_from if message_from else contact_wa_id
            user_name = contact.get("profile", {}).get("name", "") or phone_number
            
            if message_from and contact_wa_id and message_from != contact_wa_id:
                print(f"⚠️ WARNING: message.from ({message_from}) != contact.wa_id ({contact_wa_id}) – using message.from as sender")
            
            # CRITICAL FIX: Check if message is from our bot number
            if message_from and (message_from == self.source_number or message_from == f"+{self.source_number}"):
                print(f"⚠️ Ignoring message from our own bot number: {message_from}")
                return None
            
            if not phone_number:
                print(f"❌ No sender (message.from or contact.wa_id)")
                return None
            
            # Add + prefix to phone if not present
            if phone_number and not phone_number.startswith('+'):
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
                "phone_number": phone_number
            }
            
            print(f"✅ Successfully parsed Meta format webhook")
            return parsed_message
            
        except Exception as e:
            print(f"❌ ERROR parsing Meta format: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _parse_montymobile_format(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
                "timestamp": str(int(__import__('time').time())),
                "type": message_type,
                "content": self._extract_message_content(message),
                "phone_number": phone_number
            }

            return parsed_message

        except Exception as e:
            print(f"ERROR parsing MontyMobile format: {e}")
            return None

    def _parse_simple_format(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
            timestamp = webhook_data.get("timestamp", int(__import__('time').time() * 1000))

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
                audio_id = (audio_data.get("id") or audio_data.get("link") or audio_data.get("url", "")) if isinstance(audio_data, dict) else ""
                content = {"audio_id": audio_id}

            parsed_message = {
                "user_id": phone_number,
                "user_name": phone_number,  # Use phone as name for test messages
                "message_id": message_id,
                "timestamp": str(timestamp),
                "type": message_type,
                "content": content,
                "phone_number": phone_number
            }

            print(f"✅ Parsed simple format: {parsed_message}")
            return parsed_message

        except Exception as e:
            print(f"ERROR parsing simple format: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _extract_phone_from_qiscus_room(self, room: Dict[str, Any], from_user: Dict[str, Any]) -> Optional[str]:
        """Extract phone number from room information (same as Qiscus adapter)"""
        try:
            import re
            
            room_name = room.get("name", "")
            print(f"DEBUG: Checking room name for phone: {room_name}")
            
            phone_patterns = [
                r'\+(\d{1,4})\s*(\d{8,12})',
                r'(\d{1,4})\s*(\d{8,12})',
                r'\+(\d{10,15})',
                r'(\d{10,15})'
            ]
            
            for pattern in phone_patterns:
                match = re.search(pattern, room_name)
                if match:
                    if len(match.groups()) == 2:
                        country_code = match.group(1)
                        number = match.group(2)
                        phone = f"+{country_code}{number}"
                    else:
                        phone = match.group(1)
                        if not phone.startswith('+'):
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
            
            print(f"DEBUG: No phone number found in room information")
            return None
            
        except Exception as e:
            print(f"ERROR extracting phone: {e}")
            return None
    
    def _extract_message_content(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Extract message content from message format"""
        msg_type = message.get("type", "text")
        
        if msg_type == "text":
            return {"text": message.get("text", "")}
            
        elif msg_type == "file_attachment":
            payload = message.get("payload", {})
            url = payload.get("url", "")
            caption = payload.get("caption", "")
            message_text = message.get("text", "").lower()
            
            if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']):
                return {"image_id": url, "caption": caption}
            
            is_audio = (
                any(ext in url.lower() for ext in ['.mp3', '.wav', '.ogg', '.m4a', '.opus', '.oga', '.aac', '.flac']) or
                'voice' in caption.lower() or
                'audio' in caption.lower() or
                'voice' in message_text or
                'audio' in message_text or
                'ptt' in url.lower()
            )
            
            if is_audio:
                return {"audio_id": url}
            
            if any(ext in url.lower() for ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']):
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
                "address": payload.get("address", "")
            }
            
        else:
            return {"raw": message}
    
    def _get_phone_from_room_id(self, room_id: str) -> str:
        """Convert room_id to phone number if needed"""
        # If room_id looks like a phone number, use it directly
        if room_id.startswith('+') or (room_id.replace('+', '').replace('-', '').replace(' ', '').isdigit() and len(room_id) >= 8):
            return room_id
        
        # Check if we have a mapping
        if room_id in self.room_mapping:
            phone = self.room_mapping[room_id]
            if phone:
                return phone
        
        # Fallback: return room_id as-is
        print(f"WARNING: No phone mapping found for room_id {room_id}, using as-is")
        return room_id
    
    async def get_message_status(self, message_id: str) -> Dict[str, Any]:
        """Get status of a sent message"""
        return {"success": True, "status": "sent", "message": "Status tracking not available"}
    
    async def send_template_message(self, to_number: str, template_name: str, 
                                   language_code: str = "en", parameters: list = None) -> Dict[str, Any]:
        """Send a template message"""
        template_text = f"Template: {template_name}"
        if parameters:
            template_text += f"\nParameters: {', '.join(parameters)}"
        
        return await self.send_text_message(to_number, template_text)
