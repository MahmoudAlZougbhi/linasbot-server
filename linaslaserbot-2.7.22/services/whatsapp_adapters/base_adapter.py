"""
Base WhatsApp Adapter Interface
Defines the common interface for all WhatsApp providers (Meta, 360Dialog, etc.)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import httpx

class WhatsAppAdapter(ABC):
    """Base class for WhatsApp API adapters"""
    
    def __init__(self, api_token: str, phone_number_id: str = None):
        self.api_token = api_token
        self.phone_number_id = phone_number_id
        self.client = httpx.AsyncClient()
    
    @abstractmethod
    async def send_text_message(self, to_number: str, message: str) -> Dict[str, Any]:
        """Send a text message"""
        pass
    
    @abstractmethod
    async def send_image_message(self, to_number: str, image_url: str, caption: str = None) -> Dict[str, Any]:
        """Send an image message"""
        pass
    
    @abstractmethod
    async def download_media(self, media_id: str) -> bytes:
        """Download media file by ID"""
        pass
    
    @abstractmethod
    async def set_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """Set webhook URL for receiving messages"""
        pass
    
    @abstractmethod
    def parse_webhook_message(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse incoming webhook message to standard format"""
        pass
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()