"""
Base WhatsApp Adapter Interface
Defines the common interface for all WhatsApp providers (Meta, 360Dialog, etc.)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx


class WhatsAppAdapter(ABC):
    """Base class for WhatsApp API adapters"""

    provider_name: str = "unknown"

    def __init__(self, api_token: str, phone_number_id: str | None = None) -> None:
        self.api_token = api_token
        self.phone_number_id = phone_number_id
        self.client = httpx.AsyncClient()

    @abstractmethod
    async def send_text_message(self, to_number: str, message: str) -> dict[str, Any]:
        """Send a text message"""
        pass

    @abstractmethod
    async def send_image_message(self, to_number: str, image_url: str, caption: str | None = None) -> dict[str, Any]:
        """Send an image message"""
        pass

    async def send_audio_message(
        self, to_number: str, audio_url: str, audio_base64: str | None = None
    ) -> dict[str, Any]:
        """Send an audio message (optional; not all providers implement this)."""
        raise NotImplementedError("send_audio_message not supported by this adapter")

    @abstractmethod
    async def download_media(self, media_id: str) -> bytes:
        """Download media file by ID"""
        pass

    @abstractmethod
    async def set_webhook(self, webhook_url: str) -> dict[str, Any]:
        """Set webhook URL for receiving messages"""
        pass

    @abstractmethod
    def parse_webhook_message(self, webhook_data: dict[str, Any]) -> dict[str, Any] | None:
        """Parse incoming webhook message to standard format"""
        pass

    async def close(self) -> None:
        """Close HTTP client"""
        await self.client.aclose()
