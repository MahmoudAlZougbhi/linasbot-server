"""
Meta WhatsApp Adapter
Implements WhatsApp integration using Meta's WhatsApp Business API
"""
import json
from typing import Dict, Any, Optional
from .base_adapter import WhatsAppAdapter

class MetaAdapter(WhatsAppAdapter):
    """Meta WhatsApp Business API adapter"""
    
    def __init__(self, api_token: str, phone_number_id: str):
        super().__init__(api_token, phone_number_id)
        self.base_url = f"https://graph.facebook.com/v19.0/{phone_number_id}"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
    
    async def send_text_message(self, to_number: str, message: str) -> Dict[str, Any]:
        """Send a text message via Meta WhatsApp API"""
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": message}
        }
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"Meta WhatsApp message sent to {to_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending Meta WhatsApp message: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_image_message(self, to_number: str, image_url: str, caption: str = None) -> Dict[str, Any]:
        """Send an image message via Meta WhatsApp API"""
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "image",
            "image": {"link": image_url}
        }
        
        if caption:
            payload["image"]["caption"] = caption
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"Meta WhatsApp image sent to {to_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending Meta WhatsApp image: {e}")
            return {"success": False, "error": str(e)}
    
    async def download_media(self, media_id: str) -> bytes:
        """Download media file by ID from Meta WhatsApp API"""
        try:
            # First get media URL
            media_url_response = await self.client.get(
                f"https://graph.facebook.com/v19.0/{media_id}/",
                headers={"Authorization": f"Bearer {self.api_token}"}
            )
            media_url_response.raise_for_status()
            media_data = media_url_response.json()
            media_url = media_data.get("url")
            
            if not media_url:
                raise ValueError("Media URL not found in response")
            
            # Download the actual media
            media_response = await self.client.get(media_url)
            media_response.raise_for_status()
            return media_response.content
            
        except Exception as e:
            print(f"ERROR downloading Meta WhatsApp media: {e}")
            raise
    
    async def set_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """Set webhook URL for Meta WhatsApp API"""
        # Meta webhook is typically set via Facebook Developer Console
        # This is a placeholder for programmatic webhook setting if available
        print(f"Meta webhook should be set to {webhook_url} via Facebook Developer Console")
        return {"success": True, "message": "Set webhook via Facebook Developer Console"}
    
    def parse_webhook_message(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse Meta WhatsApp webhook message to standard format"""
        try:
            if "entry" in webhook_data:
                for entry in webhook_data["entry"]:
                    for change in entry.get("changes", []):
                        if change.get("field") == "messages" and change.get("value", {}).get("messages"):
                            messages = change["value"]["messages"]
                            contacts = change["value"].get("contacts", [])
                            
                            for message in messages:
                                user_id = message["from"]
                                user_name = next(
                                    (c["profile"]["name"] for c in contacts if c["wa_id"] == user_id),
                                    user_id
                                )
                                
                                return {
                                    "user_id": user_id,
                                    "user_name": user_name,
                                    "message_id": message["id"],
                                    "timestamp": message["timestamp"],
                                    "type": message["type"],
                                    "content": self._extract_message_content(message)
                                }
            return None
        except Exception as e:
            print(f"ERROR parsing Meta webhook: {e}")
            return None
    
    def _extract_message_content(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Extract message content based on type"""
        msg_type = message["type"]
        
        if msg_type == "text":
            return {"text": message["text"]["body"]}
        elif msg_type == "image":
            return {"image_id": message["image"]["id"], "caption": message["image"].get("caption")}
        elif msg_type == "audio":
            return {"audio_id": message["audio"]["id"]}
        elif msg_type == "video":
            return {"video_id": message["video"]["id"]}
        elif msg_type == "document":
            return {"document_id": message["document"]["id"], "filename": message["document"].get("filename")}
        else:
            return {"raw": message}