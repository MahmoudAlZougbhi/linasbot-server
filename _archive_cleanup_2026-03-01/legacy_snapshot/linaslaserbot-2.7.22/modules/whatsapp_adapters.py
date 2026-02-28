# -*- coding: utf-8 -*-
"""
WhatsApp adapters module: Core WhatsApp sending functions
Contains the base functions for sending messages through WhatsApp API.
"""

import httpx
from modules.core import whatsapp_api_client
from config import WHATSAPP_API_TOKEN
from services.api_integrations import log_report_event


async def send_whatsapp_message(to_number: str, message_text: str = None, image_url: str = None, audio_url: str = None):
    """Send WhatsApp message through WhatsApp API"""
    headers = {
        "Authorization": f"Bearer {WHATSAPP_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
    }

    if message_text:
        payload["type"] = "text"
        payload["text"] = {"body": message_text}
    elif image_url:
        payload["type"] = "image"
        payload["image"] = {"link": image_url}
    elif audio_url:
        payload["type"] = "audio"
        payload["audio"] = {"link": audio_url}
    else:
        print("ERROR: No message content provided for WhatsApp.")
        return False

    try:
        response = await whatsapp_api_client.post("/messages", headers=headers, json=payload)
        response.raise_for_status()
        print(f"WhatsApp message sent to {to_number}. Response: {response.json()}")
        return True
    except httpx.HTTPStatusError as e:
        print(f"ERROR sending WhatsApp message (HTTP Status {e.response.status_code}): {e.response.text}")
        log_report_event("whatsapp_send_failed", "System", "N/A", {"to": to_number, "error": e.response.text, "payload": payload})
        return False
    except httpx.RequestError as e:
        print(f"ERROR sending WhatsApp message (Request Error): {e}")
        log_report_event("whatsapp_send_failed", "System", "N/A", {"to": to_number, "error": str(e), "payload": payload})
        return False


async def send_whatsapp_typing_indicator(user_whatsapp_id: str):
    """Sends a typing indicator to WhatsApp."""
    print(f"DEBUG: WhatsApp typing indicator for {user_whatsapp_id} (simulated).\n")
