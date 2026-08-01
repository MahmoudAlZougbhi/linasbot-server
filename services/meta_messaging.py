"""Meta Messenger/Instagram webhook parsing, signature verification, and Send API adapter."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

import httpx


@dataclass(frozen=True)
class MetaMessagingSettings:
    enabled: bool
    app_secret: str
    page_id: str
    page_access_token: str
    instagram_account_id: str
    verify_token: str
    graph_api_version: str


def get_meta_messaging_settings() -> MetaMessagingSettings:
    version = (os.getenv("META_GRAPH_API_VERSION") or "v24.0").strip()
    if not version.startswith("v"):
        version = f"v{version}"
    return MetaMessagingSettings(
        enabled=(os.getenv("META_SOCIAL_MESSAGING_ENABLED") or "false").strip().lower()
        in {"1", "true", "yes"},
        app_secret=(os.getenv("META_APP_SECRET") or "").strip(),
        page_id=(os.getenv("META_PAGE_ID") or "").strip(),
        page_access_token=(os.getenv("META_PAGE_ACCESS_TOKEN") or "").strip(),
        instagram_account_id=(os.getenv("META_INSTAGRAM_ACCOUNT_ID") or "").strip(),
        verify_token=(os.getenv("META_WEBHOOK_VERIFY_TOKEN") or "").strip(),
        graph_api_version=version,
    )


def resolve_meta_send_account_id(
    channel: str,
    event: Dict[str, Any],
    settings: MetaMessagingSettings,
) -> str:
    """
    Page-linked Messenger API for Instagram uses PAGE_ID/messages with the Page access token.
    Instagram Login (no Page) falls back to META_INSTAGRAM_ACCOUNT_ID.
    """
    event_account = str(event.get("account_id") or event.get("recipient_id") or "").strip()
    if settings.page_id:
        return settings.page_id
    if str(channel or "").strip().lower() == "instagram" and settings.instagram_account_id:
        return settings.instagram_account_id
    return event_account


@dataclass
class InMemoryMessageDeduper:
    """Short-TTL in-process dedupe for Meta webhook redeliveries."""

    ttl_seconds: float = 300.0
    _seen: Dict[str, float] = field(default_factory=dict)

    def claim(self, message_id: str) -> bool:
        now = time.time()
        for mid, timestamp in list(self._seen.items()):
            if now - timestamp > self.ttl_seconds:
                self._seen.pop(mid, None)
        if message_id in self._seen:
            return False
        self._seen[message_id] = now
        return True

    def clear(self) -> None:
        self._seen.clear()


def verify_meta_signature(raw_body: bytes, signature_header: Optional[str], app_secret: str) -> bool:
    if not raw_body or not signature_header or not app_secret:
        return False
    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    received = signature_header[len(prefix) :].strip().lower()
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received, expected)


def _event_channel(
    payload_object: str,
    entry_id: str,
    recipient_id: str,
    instagram_account_id: str,
) -> str:
    if payload_object == "instagram":
        return "instagram"
    if instagram_account_id and instagram_account_id in {entry_id, recipient_id}:
        return "instagram"
    return "facebook"


def parse_meta_messaging_events(
    payload: Dict[str, Any],
    instagram_account_id: str = "",
) -> List[Dict[str, Any]]:
    """Parse Messenger Platform webhook payloads into normalized inbound events."""
    payload_object = str(payload.get("object") or "").strip().lower()
    if payload_object not in {"page", "instagram"}:
        return []

    events: List[Dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or "")
        for item in entry.get("messaging") or []:
            if not isinstance(item, dict):
                continue
            message = item.get("message") if isinstance(item.get("message"), dict) else {}
            if message.get("is_echo"):
                continue
            postback = item.get("postback") if isinstance(item.get("postback"), dict) else {}
            sender_id = str((item.get("sender") or {}).get("id") or "").strip()
            recipient_id = str((item.get("recipient") or {}).get("id") or entry_id).strip()
            if not sender_id:
                continue

            text = str(message.get("text") or postback.get("title") or postback.get("payload") or "").strip()
            attachments = message.get("attachments") if isinstance(message.get("attachments"), list) else []
            if not text and not attachments:
                continue

            message_id = str(message.get("mid") or postback.get("mid") or "").strip()
            if not message_id:
                stable = f"{payload_object}|{entry_id}|{sender_id}|{item.get('timestamp')}|{text}|{attachments}"
                message_id = "meta_synth_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:48]

            events.append(
                {
                    "channel": _event_channel(
                        payload_object, entry_id, recipient_id, instagram_account_id
                    ),
                    "sender_id": sender_id,
                    "recipient_id": recipient_id,
                    "account_id": entry_id or recipient_id,
                    "message_id": message_id,
                    "timestamp": item.get("timestamp"),
                    "text": text,
                    "attachments": attachments,
                }
            )
    return events


def split_meta_text(text: str, limit: int = 950) -> Iterable[str]:
    remaining = str(text or "").strip()
    while remaining:
        if len(remaining) <= limit:
            yield remaining
            return
        cut = remaining.rfind("\n", 0, limit + 1)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit + 1)
        if cut < limit // 2:
            cut = limit
        yield remaining[:cut].strip()
        remaining = remaining[cut:].strip()


class MetaMessagingAdapter:
    def __init__(
        self,
        access_token: str,
        account_id: str,
        channel: str,
        graph_api_version: str = "v24.0",
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.access_token = access_token
        self.account_id = account_id
        self.channel = channel
        self.graph_api_version = graph_api_version
        self.client = client or httpx.AsyncClient(timeout=20.0)
        self._owns_client = client is None

    @property
    def messages_url(self) -> str:
        return (
            f"https://graph.facebook.com/{self.graph_api_version}/"
            f"{self.account_id}/messages"
        )

    async def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = await self.client.post(
            self.messages_url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = response.text[:800]
            raise RuntimeError(
                f"Meta Send API returned HTTP {response.status_code}: {body}"
            ) from exc
        return response.json()

    async def send_text_message(self, recipient_id: str, text: str) -> Dict[str, Any]:
        responses = []
        for chunk in split_meta_text(text):
            payload: Dict[str, Any] = {
                "recipient": {"id": str(recipient_id)},
                "messaging_type": "RESPONSE",
                "message": {"text": chunk},
            }
            responses.append(await self._post(payload))
        return {"success": True, "data": responses}

    async def send_typing(self, recipient_id: str) -> Dict[str, Any]:
        if self.channel != "facebook":
            return {"success": True, "skipped": True}
        return await self._post(
            {"recipient": {"id": str(recipient_id)}, "sender_action": "typing_on"}
        )

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

