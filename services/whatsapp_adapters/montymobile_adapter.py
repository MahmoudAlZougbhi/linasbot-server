"""
MontyMobile WhatsApp Adapter
New Qiscus API endpoint using MontyMobile infrastructure

Parse mixin: montymobile_adapter_parse (LOC split).
"""

from __future__ import annotations

import json
import time
from typing import Any

from .base_adapter import WhatsAppAdapter
from .montymobile_adapter_parse import (  # noqa: F401
    MontyMobileAdapterParseMixin,
    _stable_id_when_provider_omits_message_id,
    _synthetic_wa_message_id,
)


class MontyMobileAdapter(MontyMobileAdapterParseMixin, WhatsAppAdapter):
    """MontyMobile WhatsApp API adapter (New Qiscus endpoint)"""

    def __init__(self, api_token: str, tenant_id: str, api_id: str, source_number: str, **kwargs: Any) -> None:
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
        self.base_url = "https://whatsapp-notification.montymobile.com"
        self.tenant_id = tenant_id
        self.api_id = api_id  # Keep for backward compatibility but not used in new endpoint
        self.source_number = source_number

        # MontyMobile authentication headers
        self.headers = {"Content-Type": "application/json", "Tenant": tenant_id, "api-key": api_token}

        # Store room mapping (user_id -> phone_number)
        self.room_mapping: dict[str, str] = {}

        print("✅ MontyMobile adapter initialized")
        print(f"   Base URL: {self.base_url}")
        print(f"   Tenant: {tenant_id}")
        print(f"   API ID: {api_id}")
        print(f"   Source: {source_number}")

    async def send_text_message(self, to_number: str, message: str) -> dict[str, Any]:
        """
        Send a text message via MontyMobile

        Args:
            to_number: Destination phone number (can be room_id or phone)
            message: Text message to send
        """
        # Fail closed: never send via Monty when this source number is Cloud-bound.
        try:
            from services.whatsapp_cloud.legacy_isolation import cloud_blocks_monty_send

            if cloud_blocks_monty_send(self.source_number):
                return {
                    "success": False,
                    "error": "cloud_bound_number",
                    "message": "MontyMobile send blocked for Cloud-bound WhatsApp number",
                }
        except Exception as exc:
            return {
                "success": False,
                "error": "legacy_isolation_check_failed",
                "message": f"MontyMobile send refused: isolation check failed ({exc})",
            }

        phone_number = self._get_phone_from_room_id(to_number)

        # NEW ENDPOINT - Updated from testing
        url = f"{self.base_url}/api/v2/WhatsappApi/send-session"

        # NEW PAYLOAD FORMAT - No apiId required
        payload = {"to": phone_number, "type": "TEXT", "source": self.source_number, "text": {"body": message}}

        try:
            import os

            if os.getenv("DEBUG_MONTYMOBILE", "false").lower() == "true":
                print(f"🔄 MONTYMOBILE: Sending to {phone_number[:6]}***")

            t0 = time.time()
            response = await self.client.post(url, headers=self.headers, json=payload)
            _elapsed_ms = (time.time() - t0) * 1000

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
                print("⚠️  Non-JSON response")
                if response.status_code == 200:
                    print("✅ Assuming success (HTTP 200)")
                    return {"success": True, "message": "Message sent"}
                else:
                    print(f"❌ Failed with status {response.status_code}")
                    return {"success": False, "error": f"HTTP {response.status_code}: {response_text}"}

        except Exception as e:
            print(f"\n{'=' * 80}")
            print("❌ EXCEPTION sending MontyMobile message")
            print(f"{'=' * 80}")
            print(f"❌ Error: {e}")
            print(f"❌ Error Type: {type(e).__name__}")
            import traceback

            traceback.print_exc()
            print(f"{'=' * 80}\n")
            return {"success": False, "error": str(e)}

    async def send_image_message(self, to_number: str, image_url: str, caption: str | None = None) -> dict[str, Any]:
        """
        Send an image message via MontyMobile

        Args:
            to_number: Destination phone number (can be room_id or phone)
            image_url: URL of the image to send
            caption:  caption for the image
        """
        # NEW ENDPOINT
        url = f"{self.base_url}/api/v2/WhatsappApi/send-session"

        # Convert room_id to phone number if needed
        phone_number = self._get_phone_from_room_id(to_number)

        # NEW PAYLOAD FORMAT - No apiId
        payload: dict[str, Any] = {
            "to": phone_number,
            "type": "IMAGE",
            "source": self.source_number,
            "image": {"link": image_url, "caption": caption or ""},
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
                    print("✅ Image sent successfully")
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

    async def send_audio_message(
        self, to_number: str, audio_url: str, audio_base64: str | None = None
    ) -> dict[str, Any]:
        """
        Send an audio message via MontyMobile.
        Uses the audio URL (should be Firebase/Google CDN URL for reachability).

        Args:
            to_number: Destination phone number (can be room_id or phone)
            audio_url: URL of the audio file (Firebase Storage URL)
            audio_base64:  base64-encoded audio data (unused, kept for interface compat)
        """
        phone_number = self._get_phone_from_room_id(to_number)
        send_url = f"{self.base_url}/api/v2/WhatsappApi/send-session"

        try:
            print(f"\n🔄 MONTYMOBILE: Sending audio to {phone_number}")
            print(f"📤 Audio URL: {audio_url}")

            # Attempt 1: Send as DOCUMENT type with link (AUDIO type doesn't deliver)
            print("📤 Attempt 1: Sending as DOCUMENT with link...")
            doc_payload = {
                "to": phone_number,
                "type": "DOCUMENT",
                "source": self.source_number,
                "document": {"link": audio_url, "filename": "voice_message.ogg"},
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
                    print("✅ Audio sent as DOCUMENT type")
                    return {"success": True, "data": result}
            except json.JSONDecodeError:
                pass

            # Attempt 3: Fallback to text with link
            print("📤 Attempt 3: Fallback to text with link...")
            text_payload = {
                "to": phone_number,
                "type": "TEXT",
                "source": self.source_number,
                "text": {"body": f"🎙️ Voice message: {audio_url}"},
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

    async def send_document_message(
        self, to_number: str, document_url: str, filename: str | None = None
    ) -> dict[str, Any]:
        """
        Send a document message via MontyMobile

        Args:
            to_number: Destination phone number
            document_url: URL of the document to send
            filename:  filename for the document
        """
        # NEW ENDPOINT
        url = f"{self.base_url}/api/v2/WhatsappApi/send-session"

        phone_number = self._get_phone_from_room_id(to_number)

        # NEW PAYLOAD FORMAT - No apiId
        payload: dict[str, Any] = {
            "to": phone_number,
            "type": "DOCUMENT",
            "source": self.source_number,
            "document": {"link": document_url, "filename": filename or "document"},
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

    async def send_button_message(self, to_number: str, text: str, buttons: list) -> dict[str, Any]:
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

    async def set_webhook(self, webhook_url: str, events: list | None = None) -> dict[str, Any]:
        """
        Set webhook URL for receiving messages
        Note: Webhook is configured in MontyMobile dashboard
        """
        print(f"MontyMobile webhook should be configured in dashboard: {webhook_url}")
        return {"success": True, "message": "Webhook configured in MontyMobile dashboard"}

    async def get_message_status(self, message_id: str) -> dict[str, Any]:
        """Get status of a sent message"""
        return {"success": True, "status": "sent", "message": "Status tracking not available"}

    async def send_template_message(
        self, to_number: str, template_name: str, language_code: str = "en", parameters: list | None = None
    ) -> dict[str, Any]:
        """Send a template message"""
        template_text = f"Template: {template_name}"
        if parameters:
            template_text += f"\nParameters: {', '.join(parameters)}"

        return await self.send_text_message(to_number, template_text)
