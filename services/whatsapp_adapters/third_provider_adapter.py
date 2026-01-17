"""
Qiscus WhatsApp Adapter
Qiscus Omnichannel Chat integration for WhatsApp messaging
"""
import json
from typing import Dict, Any, Optional
from .base_adapter import WhatsAppAdapter

class QiscusAdapter(WhatsAppAdapter):
    """Qiscus WhatsApp API adapter"""
    
    def __init__(self, api_token: str, app_code: str, sender_email: str, **kwargs):
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
        self.base_url = kwargs.get('base_url', 'https://omnichannel.qiscus.com')
        self.app_code = app_code
        self.sender_email = sender_email
        
        # Qiscus authentication headers
        self.headers = {
            "Content-Type": "application/json",
            "QISCUS_SDK_SECRET": api_token
        }
        
        # Store additional configuration
        self.api_version = kwargs.get('api_version', 'v1')
    
    async def send_text_message(self, to_number: str, message: str) -> Dict[str, Any]:
        """
        Send a text message via Qiscus
        
        Args:
            to_number: Room ID in Qiscus (not phone number)
            message: Text message to send
        """
        url = f"{self.base_url}/{self.app_code}/bot"
        
        payload = {
            "sender_email": self.sender_email,
            "message": message,
            "type": "text",
            "room_id": to_number  # In Qiscus, this is the room_id
        }
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"Qiscus message sent to room {to_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending Qiscus message: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_image_message(self, to_number: str, image_url: str, caption: str = None) -> Dict[str, Any]:
        """
        Send an image message via Third Provider
        
        TODO: Implement based on your provider's API documentation
        """
        url = f"{self.base_url}/messages"
        
        # TODO: Adjust payload structure based on provider requirements
        payload = {
            "to": to_number,
            "from": self.phone_number_id,
            "type": "image",
            "image": {
                "link": image_url
            }
        }
        
        if caption:
            payload["image"]["caption"] = caption
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"Third Provider image sent to {to_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending Third Provider image: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_audio_message(self, to_number: str, audio_url: str) -> Dict[str, Any]:
        """
        Send an audio message via Third Provider
        
        TODO: Implement if your provider supports audio messages
        """
        url = f"{self.base_url}/messages"
        
        payload = {
            "to": to_number,
            "from": self.phone_number_id,
            "type": "audio",
            "audio": {
                "link": audio_url
            }
        }
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"Third Provider audio sent to {to_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending Third Provider audio: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_document_message(self, to_number: str, document_url: str, filename: str = None) -> Dict[str, Any]:
        """
        Send a document message via Third Provider
        
        TODO: Implement if your provider supports document messages
        """
        url = f"{self.base_url}/messages"
        
        payload = {
            "to": to_number,
            "from": self.phone_number_id,
            "type": "document",
            "document": {
                "link": document_url
            }
        }
        
        if filename:
            payload["document"]["filename"] = filename
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"Third Provider document sent to {to_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending Third Provider document: {e}")
            return {"success": False, "error": str(e)}
    
    async def download_media(self, media_id: str) -> bytes:
        """
        Download media file by ID
        
        TODO: Implement based on your provider's media download API
        """
        try:
            # Example implementation - adjust based on your provider
            # Some providers might require different endpoints or authentication
            media_url = f"{self.base_url}/media/{media_id}"
            
            response = await self.client.get(media_url, headers=self.headers)
            response.raise_for_status()
            
            # Some providers return a URL that needs to be downloaded separately
            if response.headers.get('content-type') == 'application/json':
                media_data = response.json()
                actual_url = media_data.get('url') or media_data.get('download_url')
                if actual_url:
                    media_response = await self.client.get(actual_url)
                    media_response.raise_for_status()
                    return media_response.content
            
            return response.content
            
        except Exception as e:
            print(f"ERROR downloading Third Provider media: {e}")
            raise
    
    async def set_webhook(self, webhook_url: str, events: list = None) -> Dict[str, Any]:
        """
        Set webhook URL for receiving messages
        
        TODO: Implement based on your provider's webhook configuration API
        """
        # Example implementation - adjust based on your provider
        url = f"{self.base_url}/webhooks"
        
        payload = {
            "url": webhook_url,
            "events": events or ["message.received", "message.status", "message.failed"]
        }
        
        # Some providers might require verification token
        if hasattr(self, 'webhook_verify_token'):
            payload["verify_token"] = self.webhook_verify_token
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"Third Provider webhook set to {webhook_url}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR setting Third Provider webhook: {e}")
            return {"success": False, "error": str(e)}
    
    def parse_webhook_message(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse incoming webhook message to standard format
        
        TODO: Implement based on your provider's webhook payload structure
        """
        try:
            # Example parsing - adjust based on your provider's webhook format
            # Different providers have different webhook structures
            
            # Example 1: Provider sends messages in a 'messages' array
            if "messages" in webhook_data:
                for message in webhook_data["messages"]:
                    return self._parse_message(message, webhook_data)
            
            # Example 2: Provider sends single message object
            elif "message" in webhook_data:
                return self._parse_message(webhook_data["message"], webhook_data)
            
            # Example 3: Provider sends data in 'data' field
            elif "data" in webhook_data:
                data = webhook_data["data"]
                if "message" in data:
                    return self._parse_message(data["message"], webhook_data)
            
            # Example 4: Direct message format
            elif "from" in webhook_data and "type" in webhook_data:
                return self._parse_message(webhook_data, webhook_data)
            
            print(f"Unknown webhook format from Third Provider: {webhook_data}")
            return None
            
        except Exception as e:
            print(f"ERROR parsing Third Provider webhook: {e}")
            return None
    
    def _parse_message(self, message: Dict[str, Any], full_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Helper to parse individual message
        
        TODO: Adjust field names based on your provider's format
        """
        # Extract user information
        user_id = message.get("from") or message.get("sender") or message.get("phone_number")
        
        # Try to get user name from contacts or profile
        user_name = user_id  # Default to phone number
        if "contacts" in full_data:
            for contact in full_data["contacts"]:
                if contact.get("wa_id") == user_id or contact.get("phone") == user_id:
                    user_name = contact.get("profile", {}).get("name", user_id)
                    break
        elif "profile" in message:
            user_name = message["profile"].get("name", user_id)
        
        return {
            "user_id": user_id,
            "user_name": user_name,
            "message_id": message.get("id") or message.get("message_id"),
            "timestamp": message.get("timestamp") or message.get("created_at"),
            "type": message.get("type") or "text",
            "content": self._extract_message_content(message)
        }
    
    def _extract_message_content(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract message content based on type
        
        TODO: Adjust based on your provider's message structure
        """
        msg_type = message.get("type", "text")
        
        if msg_type == "text":
            # Different providers might use different field names
            text = (message.get("text", {}).get("body") or 
                   message.get("body") or 
                   message.get("content") or 
                   message.get("message"))
            return {"text": text}
            
        elif msg_type == "image":
            return {
                "image_id": message.get("image", {}).get("id") or message.get("media_id"),
                "caption": message.get("image", {}).get("caption") or message.get("caption")
            }
            
        elif msg_type == "audio":
            return {
                "audio_id": message.get("audio", {}).get("id") or message.get("media_id")
            }
            
        elif msg_type == "video":
            return {
                "video_id": message.get("video", {}).get("id") or message.get("media_id"),
                "caption": message.get("video", {}).get("caption")
            }
            
        elif msg_type == "document":
            return {
                "document_id": message.get("document", {}).get("id") or message.get("media_id"),
                "filename": message.get("document", {}).get("filename")
            }
            
        elif msg_type == "location":
            location = message.get("location", {})
            return {
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "name": location.get("name"),
                "address": location.get("address")
            }
            
        else:
            # Return raw message for unknown types
            return {"raw": message}
    
    async def get_message_status(self, message_id: str) -> Dict[str, Any]:
        """
        Get status of a sent message (delivered, read, failed, etc.)
        
        TODO: Implement if your provider supports message status queries
        """
        url = f"{self.base_url}/messages/{message_id}/status"
        
        try:
            response = await self.client.get(url, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR getting message status from Third Provider: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_template_message(self, to_number: str, template_name: str, 
                                   language_code: str = "en", parameters: list = None) -> Dict[str, Any]:
        """
        Send a pre-approved template message
        
        TODO: Implement if your provider supports template messages
        """
        url = f"{self.base_url}/messages"
        
        payload = {
            "to": to_number,
            "from": self.phone_number_id,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code
                }
            }
        }
        
        if parameters:
            payload["template"]["components"] = [{
                "type": "body",
                "parameters": [{"type": "text", "text": param} for param in parameters]
            }]
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"Third Provider template sent to {to_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending Third Provider template: {e}")
            return {"success": False, "error": str(e)}