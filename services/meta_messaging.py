"""Meta Messenger/Instagram webhook parsing, signature verification, and Send API adapter."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

from services.meta_app_registry import get_meta_graph_api_version

META_MESSAGING_PLATFORM_KEYS: tuple[str, ...] = (
    "app_id_configured",
    "app_id_allowed_for_mode",
    "app_secret_configured",
    "verify_token_configured",
    "graph_api_version_allowlisted",
)


@dataclass(frozen=True)
class MetaMessagingSettings:
    enabled: bool
    app_secret: str
    page_id: str
    page_access_token: str
    instagram_account_id: str
    verify_token: str
    graph_api_version: str
    app_id: str = ""
    app_key: str = "linas_first_party"
    tenant_id: str = ""
    binding_id: str = ""
    auth_flow: str = "facebook_login"
    graph_base_url: str = "https://graph.facebook.com"


def get_meta_messaging_settings() -> MetaMessagingSettings:
    version = get_meta_graph_api_version()
    return MetaMessagingSettings(
        enabled=(os.getenv("META_SOCIAL_MESSAGING_ENABLED") or "false").strip().lower() in {"1", "true", "yes"},
        app_secret=(os.getenv("META_APP_SECRET") or "").strip(),
        page_id=(os.getenv("META_PAGE_ID") or "").strip(),
        page_access_token=(os.getenv("META_PAGE_ACCESS_TOKEN") or "").strip(),
        instagram_account_id=(os.getenv("META_INSTAGRAM_ACCOUNT_ID") or "").strip(),
        verify_token=(os.getenv("META_WEBHOOK_VERIFY_TOKEN") or "").strip(),
        graph_api_version=version,
        app_id=(os.getenv("META_APP_ID") or "").strip(),
    )


def get_meta_messaging_readiness(settings: MetaMessagingSettings | None = None) -> tuple[bool, dict[str, bool]]:
    """Boolean-only platform readiness for the legacy single-app Meta path.

    Page/Instagram allowlist identity is diagnostic only and must not fail
    platform readiness. Facebook-only or Instagram-only remains platform-ready.
    """

    current = settings or get_meta_messaging_settings()
    app_id = (os.getenv("META_APP_ID") or "").strip()
    rollback_active = (os.getenv("META_SOCIAL_ROLLBACK_ACTIVE") or "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    new_app_required = (os.getenv("META_SOCIAL_NEW_APP_REQUIRED") or "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    retired_app_allowed = not new_app_required or rollback_active
    checks = {
        "app_id_configured": bool(app_id),
        "app_id_allowed_for_mode": bool(app_id and (app_id != "1784792718776344" or retired_app_allowed)),
        "app_secret_configured": bool(current.app_secret),
        "page_access_token_configured": bool(current.page_access_token),
        "verify_token_configured": bool(current.verify_token),
        "page_id_allowlisted": current.page_id == "378696005334409",
        "instagram_id_allowlisted": current.instagram_account_id == "17841413184256533",
        "graph_api_version_allowlisted": current.graph_api_version == "v24.0",
    }
    platform_ok = all(bool(checks[key]) for key in META_MESSAGING_PLATFORM_KEYS)
    return platform_ok, checks


def resolve_meta_send_account_id(
    channel: str,
    event: dict[str, Any],
    settings: MetaMessagingSettings,
) -> str:
    """
    Page-linked Messenger API for Instagram uses PAGE_ID/messages with the Page access token.
    Instagram Login uses graph.instagram.com /{ig_user_id}/messages per Meta docs.
    """
    if settings.auth_flow == "instagram_login" and str(channel or "").strip().lower() == "instagram":
        return settings.instagram_account_id or str(event.get("account_id") or event.get("recipient_id") or "").strip()
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
    _seen: dict[str, float] = field(default_factory=dict)

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


def verify_meta_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
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


def _account_allowed_for_channel(
    channel: str,
    entry_id: str,
    recipient_id: str,
    page_id: str,
    instagram_account_id: str,
) -> bool:
    """Reject events that do not belong to the configured Page / Instagram account."""
    page_id = (page_id or "").strip()
    instagram_account_id = (instagram_account_id or "").strip()
    ids = {entry_id, recipient_id}
    if channel == "facebook":
        if not page_id:
            return False
        return page_id in ids
    if channel == "instagram":
        if not instagram_account_id:
            return False
        # Page-linked Instagram deliveries may use either the IG account id or Page id.
        allowed = {instagram_account_id, page_id} if page_id else {instagram_account_id}
        return bool(ids & allowed)
    return False


def parse_meta_messaging_events(
    payload: dict[str, Any],
    instagram_account_id: str = "",
    page_id: str = "",
) -> list[dict[str, Any]]:
    """Parse Messenger Platform webhook payloads into normalized inbound events.

    Only Facebook Page (`object=page`) and Instagram (`object=instagram`) events are
    accepted. WhatsApp Cloud / other Meta objects yield an empty list so they cannot
    invoke the social AI pipeline. Page Inbox handover delivers user DMs on
    ``entry.standby``; those are parsed the same as ``entry.messaging``. When
    page_id / instagram_account_id are provided, events for any other account are dropped.
    """
    payload_object = str(payload.get("object") or "").strip().lower()
    if payload_object in {"whatsapp_business_account", "whatsapp"}:
        return []
    if payload_object not in {"page", "instagram"}:
        return []

    events: list[dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or "")
        inbound = list(entry.get("messaging") or []) + list(entry.get("standby") or [])
        for item in inbound:
            if not isinstance(item, dict):
                continue
            message = item.get("message")
            message_dict: dict[str, Any] = message if isinstance(message, dict) else {}
            if message_dict.get("is_echo"):
                continue
            postback_raw = item.get("postback")
            postback: dict[str, Any] = postback_raw if isinstance(postback_raw, dict) else {}
            sender_candidate = item.get("sender")
            sender_raw: dict[str, Any] = sender_candidate if isinstance(sender_candidate, dict) else {}
            sender_id = str(sender_raw.get("id") or "").strip()
            recipient_id = str((item.get("recipient") or {}).get("id") or entry_id).strip()
            if not sender_id:
                continue
            # Defense in depth: reject account-originated/self deliveries even if
            # Meta omits is_echo on a malformed or unexpected event.
            configured_accounts = {value for value in (page_id, instagram_account_id, entry_id) if value}
            if sender_id in configured_accounts:
                continue

            text = str(message_dict.get("text") or postback.get("title") or postback.get("payload") or "").strip()
            attachments_raw = message_dict.get("attachments")
            attachments = attachments_raw if isinstance(attachments_raw, list) else []
            if not text and not attachments:
                continue

            message_id = str(message_dict.get("mid") or postback.get("mid") or "").strip()
            if not message_id:
                stable = f"{payload_object}|{entry_id}|{sender_id}|{item.get('timestamp')}|{text}|{attachments}"
                message_id = "meta_synth_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:48]

            channel = _event_channel(payload_object, entry_id, recipient_id, instagram_account_id)
            if page_id or instagram_account_id:
                if not _account_allowed_for_channel(channel, entry_id, recipient_id, page_id, instagram_account_id):
                    continue

            # Best-effort: some Meta payloads include participant labels on sender.
            # Never invent; Graph User Profile remains the primary name source.
            sender_name = str(sender_raw.get("name") or "").strip()
            sender_username = str(sender_raw.get("username") or "").strip()
            event: dict[str, Any] = {
                "channel": channel,
                "sender_id": sender_id,
                "recipient_id": recipient_id,
                "account_id": entry_id or recipient_id,
                "message_id": message_id,
                "timestamp": item.get("timestamp"),
                "text": text,
                "attachments": attachments,
                "is_postback": bool(postback),
            }
            if sender_name:
                event["sender_name"] = sender_name
            if sender_username:
                event["sender_username"] = sender_username
            events.append(event)
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


# Channel-scoped labels that must never be treated as a real Meta participant name.
# Legacy hardcodes ("Instagram Customer" / "Facebook Customer") are included so
# stored conversations refresh instead of greeting with the placeholder forever.
UNRESOLVED_SOCIAL_DISPLAY_NAMES = frozenset(
    {
        "instagram customer",
        "facebook customer",
        "unknown customer",
        "client",
        "customer",
        "guest",
        "user",
        "anonymous",
        "not known",
        "n/a",
        "na",
        "test user",
        "new user",
    }
)
SOCIAL_DISPLAY_NAME_FALLBACK = "Customer"


def is_unresolved_social_display_name(name: str | None) -> bool:
    """True when the value is empty or a non-personal placeholder label."""
    cleaned = str(name or "").strip()
    if not cleaned:
        return True
    lowered = cleaned.lower()
    if lowered in UNRESOLVED_SOCIAL_DISPLAY_NAMES:
        return True
    if lowered.startswith("test user"):
        return True
    return False


def pick_meta_participant_display_name(
    *,
    name: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
) -> str | None:
    """
    Choose a display name from Meta-provided profile fields only.

    Prefer full name, then first(+last), then Instagram username. Never invent.
    """
    candidates: list[str] = []
    full = str(name or "").strip()
    if full:
        candidates.append(full)
    first = str(first_name or "").strip()
    last = str(last_name or "").strip()
    if first and last:
        candidates.append(f"{first} {last}")
    elif first:
        candidates.append(first)
    handle = str(username or "").strip().lstrip("@")
    if handle:
        candidates.append(handle)
    for candidate in candidates:
        if not is_unresolved_social_display_name(candidate):
            return candidate
    return None


def normalize_social_display_name(name: str | None, *, fallback: str = SOCIAL_DISPLAY_NAME_FALLBACK) -> str:
    """Map unresolved / legacy placeholders to an honest fallback for UI and prompts."""
    cleaned = str(name or "").strip()
    if is_unresolved_social_display_name(cleaned):
        return fallback
    return cleaned


def scrub_legacy_meta_channel_placeholder(name: str | None) -> str:
    """
    Replace only the historical channel-branded labels in stored UI data.

    Other unresolved labels (e.g. WhatsApp \"Unknown Customer\") are left intact
    so Live Chat behavior outside Meta social stays unchanged.
    """
    cleaned = str(name or "").strip()
    if cleaned.lower() in {"instagram customer", "facebook customer"}:
        return SOCIAL_DISPLAY_NAME_FALLBACK
    return cleaned


class MetaMessagingAdapter:
    def __init__(
        self,
        access_token: str,
        account_id: str,
        channel: str,
        graph_api_version: str = "v24.0",
        client: httpx.AsyncClient | None = None,
        graph_base_url: str = "https://graph.facebook.com",
    ):
        self.access_token = access_token
        self.account_id = account_id
        self.channel = channel
        self.graph_api_version = graph_api_version
        self.graph_base_url = graph_base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=20.0)
        self._owns_client = client is None

    @property
    def messages_url(self) -> str:
        return f"{self.graph_base_url}/{self.graph_api_version}/{self.account_id}/messages"

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
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
            from services.omnichannel.meta_errors import raise_from_meta_response

            raise_from_meta_response(response)
            raise RuntimeError("meta_send_failed") from exc
        return cast(dict[str, Any], response.json())

    async def send_text_message(self, recipient_id: str, text: str) -> dict[str, Any]:
        message_ids: list[str] = []
        for chunk in split_meta_text(text):
            payload: dict[str, Any] = {
                "recipient": {"id": str(recipient_id)},
                "messaging_type": "RESPONSE",
                "message": {"text": chunk},
            }
            response = await self._post(payload)
            message_id = str(response.get("message_id") or "").strip()
            if not message_id:
                return {
                    "success": False,
                    "provider": "meta",
                    "error": "meta_send_missing_message_id",
                }
            message_ids.append(message_id)
        return {
            "success": True,
            "provider": "meta",
            "message_id": message_ids[-1],
            "message_ids": message_ids,
        }

    async def send_typing(self, recipient_id: str) -> dict[str, Any]:
        if self.channel != "facebook":
            return {"success": True, "skipped": True}
        return await self._post({"recipient": {"id": str(recipient_id)}, "sender_action": "typing_on"})

    async def fetch_participant_profile(self, participant_id: str) -> dict[str, Any]:
        """
        Fetch messaging participant profile fields Meta exposes for this channel.

        Facebook PSID: name / first_name / last_name (User Profile API).
        Instagram IGSID: name / username.
        Returns an empty dict when the profile is unavailable (privacy, permissions,
        or transient Graph errors) — callers must use an honest fallback.
        """
        pid = str(participant_id or "").strip()
        if not pid or not self.access_token:
            return {}
        fields = "name,username" if str(self.channel or "").lower() == "instagram" else "name,first_name,last_name"
        url = f"{self.graph_base_url}/{self.graph_api_version}/{pid}"
        try:
            response = await self.client.get(
                url,
                params={"fields": fields, "access_token": self.access_token},
            )
            if response.status_code >= 400:
                # Do not log body or participant id — may contain PII / identifiers.
                return {}
            payload = response.json()
            if not isinstance(payload, dict):
                return {}
            if payload.get("error"):
                return {}
            return {
                "name": str(payload.get("name") or "").strip() or None,
                "first_name": str(payload.get("first_name") or "").strip() or None,
                "last_name": str(payload.get("last_name") or "").strip() or None,
                "username": str(payload.get("username") or "").strip() or None,
            }
        except (httpx.HTTPError, TypeError, ValueError):
            return {}

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()
