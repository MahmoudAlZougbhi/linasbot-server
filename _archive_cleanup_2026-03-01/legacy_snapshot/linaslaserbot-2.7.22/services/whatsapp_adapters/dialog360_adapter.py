"""
360Dialog WhatsApp Adapter
Implements WhatsApp integration using 360Dialog API
"""
import json
from typing import Dict, Any, Optional
from .base_adapter import WhatsAppAdapter

class Dialog360Adapter(WhatsAppAdapter):
    """360Dialog WhatsApp API adapter"""
    
    def __init__(self, api_token: str, is_sandbox: bool = True):
        super().__init__(api_token)
        self.is_sandbox = is_sandbox
        self.base_url = "https://waba-sandbox.360dialog.io/v1" if is_sandbox else "https://waba.360dialog.io/v1"
        self.headers = {
            "D360-API-KEY": api_token,
            "Content-Type": "application/json"
        }
    
    async def send_text_message(self, to_number: str, message: str) -> Dict[str, Any]:
        """Send a text message via 360Dialog"""
        url = f"{self.base_url}/messages"
        payload = {
            "to": to_number,
            "type": "text",
            "text": {
                "body": message
            }
        }
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"360Dialog message sent to {to_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending 360Dialog message: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_image_message(self, to_number: str, image_url: str, caption: str = None) -> Dict[str, Any]:
        """Send an image message via 360Dialog"""
        url = f"{self.base_url}/messages"
        payload = {
            "to": to_number,
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
            print(f"360Dialog image sent to {to_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending 360Dialog image: {e}")
            return {"success": False, "error": str(e)}
    
    async def download_media(self, media_id: str) -> bytes:
        """Download media file by ID (360Dialog specific implementation)"""
        # 360Dialog media download implementation would go here
        # This is a placeholder - actual implementation depends on 360Dialog's media API
        raise NotImplementedError("360Dialog media download not yet implemented")
    
    async def set_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """Set webhook URL for 360Dialog"""
        url = f"{self.base_url}/configs/webhook"
        payload = {"url": webhook_url}
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"360Dialog webhook set to {webhook_url}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR setting 360Dialog webhook: {e}")
            return {"success": False, "error": str(e)}
    
    def parse_webhook_message(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse 360Dialog webhook message to standard format"""
        try:
            # 360Dialog webhook format is similar to Meta's
            if "messages" in webhook_data:
                for message in webhook_data["messages"]:
                    return {
                        "user_id": message["from"],
                        "user_name": webhook_data.get("contacts", [{}])[0].get("profile", {}).get("name", message["from"]),
                        "message_id": message["id"],
                        "timestamp": message["timestamp"],
                        "type": message["type"],
                        "content": self._extract_message_content(message)
                    }
            return None
        except Exception as e:
            print(f"ERROR parsing 360Dialog webhook: {e}")
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
    
    async def send_template_message(self, to_number: str, template_name: str, language_code: str = "en", parameters: list = None) -> Dict[str, Any]:
        """Send a template message (360Dialog specific)"""
        url = f"{self.base_url}/messages"
        payload = {
            "to": to_number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code
                }
            }
        }
        
        # Add parameters if provided
        if parameters:
            payload["template"]["components"] = [{
                "type": "body",
                "parameters": [{"type": "text", "text": param} for param in parameters]
            }]
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"360Dialog template sent to {to_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending 360Dialog template: {e}")
            return {"success": False, "error": str(e)}