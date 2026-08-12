"""
Qiscus WhatsApp Adapter
Qiscus Omnichannel Chat integration for WhatsApp messaging

Parse mixin: qiscus_adapter_parse (LOC split).
"""

from __future__ import annotations

import json
from typing import Any, cast

from .base_adapter import WhatsAppAdapter
from .qiscus_adapter_parse import QiscusAdapterParseMixin


class QiscusAdapter(QiscusAdapterParseMixin, WhatsAppAdapter):
    """Qiscus WhatsApp API adapter"""

    def __init__(self, api_token: str, app_code: str, sender_email: str, **kwargs: Any) -> None:
        """
        Initialize the Qiscus adapter

        Args:
            api_token: QISCUS_SDK_SECRET for authentication
            app_code: Qiscus App Code (AppCode)
            sender_email: Admin email for sending messages
            **kwargs: Additional Qiscus-specific configuration
        """
        super().__init__(api_token, app_code)  # Use app_code as phone_number_id equivalent

        # Qiscus API configuration
        self.base_url = kwargs.get("base_url", "https://omnichannel.qiscus.com")
        self.app_code = app_code
        self.sender_email = sender_email

        # Qiscus authentication headers
        self.headers = {"Content-Type": "application/json", "QISCUS_SDK_SECRET": api_token}

        # Store additional configuration
        self.api_version = kwargs.get("api_version", "v1")

        # Store room mapping (user_id -> room_id)
        self.room_mapping: dict[str, str] = {}

    async def send_text_message(self, to_number: str, message: str) -> dict[str, Any]:
        """
        Send a text message via Qiscus

        Args:
            to_number: Room ID in Qiscus (not phone number)
            message: Text message to send
        """
        url = f"{self.base_url}/{self.app_code}/bot"

        payload: dict[str, Any] = {
            "sender_email": self.sender_email,
            "message": message,
            "type": "text",
            "room_id": to_number,  # In Qiscus, this is the room_id
        }

        try:
            print(f"🔄 Sending Qiscus message to room ***{str(to_number)[-4:] if to_number else ''}")
            print(f"📤 URL: {url}")
            print(f"📤 Payload: {payload}")

            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()

            # Check if response has content
            response_text = response.text
            print(f"📥 Response status: {response.status_code}")
            print(f"📥 Response text: {response_text}")

            if response_text:
                try:
                    result = response.json()
                    print(f"✅ Qiscus message sent to room ***{str(to_number)[-4:] if to_number else ''}. status=ok")
                    return {"success": True, "data": result}
                except json.JSONDecodeError as json_err:
                    print(f"⚠️ Response is not JSON: {json_err}")
                    # If response is not JSON but status is 200, consider it success
                    if response.status_code == 200:
                        print("✅ Message sent successfully (non-JSON response)")
                        return {"success": True, "message": "Message sent"}
                    else:
                        return {"success": False, "error": f"Invalid JSON response: {response_text}"}
            else:
                # Empty response but 200 status
                if response.status_code == 200:
                    print("✅ Message sent successfully (empty response)")
                    return {"success": True, "message": "Message sent"}
                else:
                    return {"success": False, "error": "Empty response from Qiscus"}

        except Exception as e:
            print(f"❌ ERROR sending Qiscus message: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}

    async def send_image_message(self, to_number: str, image_url: str, caption: str | None = None) -> dict[str, Any]:
        """
        Send an image message via Qiscus for WhatsApp

        Tries both file_attachment type and text URL approach.
        Since Qiscus might not forward file_attachment to WhatsApp clients,
        we fall back to sending URL directly. WhatsApp will auto-detect
        image extension and display as gallery item.

        Args:
            to_number: Room ID in Qiscus
            image_url: URL of the image to send
            caption:  caption for the image
        """
        url = f"{self.base_url}/{self.app_code}/bot"

        # Approach 1: Try file_attachment type first
        payload_attachment = {
            "sender_email": self.sender_email,
            "message": caption or "Image",
            "type": "file_attachment",
            "room_id": to_number,
            "payload": {"url": image_url, "caption": caption or ""},
        }

        # Approach 2: Fallback - send as text message with URL (WhatsApp auto-detects image)
        payload_text = {
            "sender_email": self.sender_email,
            "message": f"{caption}\n{image_url}" if caption else image_url,  # URL with optional caption
            "type": "text",
            "room_id": to_number,
        }

        try:
            print(f"🔄 Sending Qiscus image to room ***{str(to_number)[-4:] if to_number else ''}")
            print(f"📤 Image URL: {image_url}")
            if caption:
                print(f"📤 Caption: {caption}")

            # First, try with file_attachment type
            print("📤 Attempt 1: Trying file_attachment type...")
            print(f"📤 Payload: {payload_attachment}")

            response = await self.client.post(url, headers=self.headers, json=payload_attachment)

            # Check response
            response_text = response.text
            print(f"📥 Response status: {response.status_code}")
            print(f"📥 Response text: {response_text[:200]}")  # Truncate long responses

            if response.status_code == 200:
                try:
                    result = response.json()
                    print("✅ Image sent via file_attachment. status=ok")
                    return {"success": True, "data": result, "method": "file_attachment"}
                except json.JSONDecodeError:
                    # 200 status but non-JSON response is still success
                    print("✅ Image sent via file_attachment (non-JSON response)")
                    return {"success": True, "message": "Message sent", "method": "file_attachment"}
            else:
                # If file_attachment fails, try sending as text URL
                print(f"⚠️ file_attachment failed with status {response.status_code}, trying text URL...")
                print("📤 Attempt 2: Trying text message with image URL...")
                print(f"📤 Payload: {payload_text}")

                response2 = await self.client.post(url, headers=self.headers, json=payload_text)
                response_text2 = response2.text
                print(f"📥 Response status: {response2.status_code}")
                print(f"📥 Response text: {response_text2[:200]}")

                if response2.status_code == 200:
                    try:
                        result = response2.json()
                        print("✅ Image sent as text URL. status=ok")
                        return {"success": True, "data": result, "method": "text_url"}
                    except json.JSONDecodeError:
                        print("✅ Image sent as text URL (non-JSON response)")
                        return {"success": True, "message": "Message sent", "method": "text_url"}
                else:
                    return {
                        "success": False,
                        "error": f"Both methods failed. Statuses: {response.status_code}, {response2.status_code}",
                    }

        except Exception as e:
            print(f"❌ ERROR sending Qiscus image: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}

    async def send_audio_message(
        self, to_number: str, audio_url: str, audio_base64: str | None = None
    ) -> dict[str, Any]:
        """
        Send an audio message via Qiscus for WhatsApp

        Since Qiscus Bot API might not forward file_attachment type to WhatsApp,
        we send the URL directly as text message. WhatsApp will auto-detect
        .opus extension and convert it to playable audio icon.

        Args:
            to_number: Room ID in Qiscus
            audio_url: URL of the audio file (.opus format)
        """
        url = f"{self.base_url}/{self.app_code}/bot"

        # Try BOTH approaches: first file_attachment, then fallback to URL text
        # This gives us the best chance of working across different Qiscus configs

        # Approach 1: Try file_attachment type first
        payload_attachment = {
            "sender_email": self.sender_email,
            "message": "🎙️ Voice Message",  # Fallback text if media fails
            "type": "file_attachment",
            "room_id": to_number,
            "payload": {"url": audio_url, "caption": "Voice Message"},
        }

        # Approach 2: Fallback - send as text message with URL (WhatsApp auto-detects .opus)
        payload_text = {
            "sender_email": self.sender_email,
            "message": audio_url,  # Just the URL - WhatsApp recognizes .opus extension
            "type": "text",
            "room_id": to_number,
        }

        try:
            print(f"🔄 Sending Qiscus audio message to room ***{str(to_number)[-4:] if to_number else ''}")
            print(f"📤 Audio URL: {audio_url}")

            # First, try with file_attachment type
            print("📤 Attempt 1: Trying file_attachment type...")
            print(f"📤 Payload: {payload_attachment}")

            response = await self.client.post(url, headers=self.headers, json=payload_attachment)

            # Check response
            response_text = response.text
            print(f"📥 Response status: {response.status_code}")
            print(f"📥 Response text: {response_text[:200]}")  # Truncate long responses

            if response.status_code == 200:
                try:
                    result = response.json()
                    print("✅ Audio sent via file_attachment. status=ok")
                    return {"success": True, "data": result, "method": "file_attachment"}
                except json.JSONDecodeError:
                    # 200 status but non-JSON response is still success
                    print("✅ Audio sent via file_attachment (non-JSON response)")
                    return {"success": True, "message": "Message sent", "method": "file_attachment"}
            else:
                # If file_attachment fails, try sending as text URL
                print(f"⚠️ file_attachment failed with status {response.status_code}, trying text URL...")
                print("📤 Attempt 2: Trying text message with .opus URL...")
                print(f"📤 Payload: {payload_text}")

                response2 = await self.client.post(url, headers=self.headers, json=payload_text)
                response_text2 = response2.text
                print(f"📥 Response status: {response2.status_code}")
                print(f"📥 Response text: {response_text2[:200]}")

                if response2.status_code == 200:
                    try:
                        result = response2.json()
                        print("✅ Audio sent as text URL (.opus). status=ok")
                        return {"success": True, "data": result, "method": "text_url"}
                    except json.JSONDecodeError:
                        print("✅ Audio sent as text URL (.opus) (non-JSON response)")
                        return {"success": True, "message": "Message sent", "method": "text_url"}
                else:
                    return {
                        "success": False,
                        "error": f"Both methods failed. Statuses: {response.status_code}, {response2.status_code}",
                    }

        except Exception as e:
            print(f"❌ ERROR sending Qiscus audio: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}

    async def send_document_message(
        self, to_number: str, document_url: str, filename: str | None = None
    ) -> dict[str, Any]:
        """
        Send a document message via Qiscus

        Args:
            to_number: Room ID in Qiscus
            document_url: URL of the document to send
            filename:  filename for the document
        """
        url = f"{self.base_url}/{self.app_code}/bot"

        payload: dict[str, Any] = {
            "sender_email": self.sender_email,
            "message": filename or "Document",
            "type": "file_attachment",
            "room_id": to_number,
            "payload": {"url": document_url, "caption": filename or "Document"},
        }

        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"Qiscus document sent to room ***{str(to_number)[-4:] if to_number else ''}. status=ok")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending Qiscus document: {e}")
            return {"success": False, "error": str(e)}

    async def send_button_message(self, to_number: str, text: str, buttons: list) -> dict[str, Any]:
        """
        Send a button message via Qiscus
        Note: Buttons are not supported for WhatsApp in Qiscus

        Args:
            to_number: Room ID in Qiscus
            text: Button message text
            buttons: List of button objects
        """
        # Since buttons are not supported for WhatsApp in Qiscus, send as text
        button_text = f"{text}\n\n"
        for i, button in enumerate(buttons, 1):
            button_text += f"{i}. {button.get('label', 'Option')}\n"

        return await self.send_text_message(to_number, button_text)

    async def download_media(self, media_id: str) -> bytes:
        """
        Download media file by ID
        Note: Qiscus handles media differently - URLs are provided directly
        """
        try:
            # In Qiscus, media URLs are provided directly in the webhook
            # This method might not be needed as URLs are direct
            response = await self.client.get(media_id)  # media_id is actually the URL
            response.raise_for_status()
            return response.content

        except Exception as e:
            print(f"ERROR downloading Qiscus media: {e}")
            raise

    async def set_webhook(self, webhook_url: str, events: list | None = None) -> dict[str, Any]:
        """
        Set webhook URL for receiving messages
        Note: Webhook is configured in Qiscus dashboard, not via API
        """
        print(f"Qiscus webhook should be configured in dashboard: {webhook_url}")
        return {"success": True, "message": "Webhook configured in Qiscus dashboard"}

    async def get_message_status(self, message_id: str) -> dict[str, Any]:
        """
        Get status of a sent message
        Note: Qiscus doesn't provide direct message status API
        """
        return {"success": True, "status": "sent", "message": "Status tracking not available in Qiscus"}

    async def send_template_message(
        self, to_number: str, template_name: str, language_code: str = "en", parameters: list | None = None
    ) -> dict[str, Any]:
        """
        Send a template message
        Note: Qiscus doesn't have template messages, send as regular text
        """
        # Convert template to regular text message
        template_text = f"Template: {template_name}"
        if parameters:
            template_text += f"\nParameters: {', '.join(parameters)}"

        return await self.send_text_message(to_number, template_text)

    def get_room_id_for_user(self, user_id: str) -> str:
        """
        Get room ID for a user (helper method)
        """
        return cast(str, self.room_mapping.get(user_id, user_id))
