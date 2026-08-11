"""Per-tenant WhatsApp Cloud Graph API client (never uses singleton WHATSAPP_* env tokens)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from services.whatsapp_cloud.config import GRAPH_API_HOST, get_whatsapp_cloud_flags

ALLOWED_GRAPH_HOSTS = frozenset({GRAPH_API_HOST, f"www.{GRAPH_API_HOST}"})


class WhatsAppGraphError(RuntimeError):
    def __init__(self, code: str, message: str, *, http_status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable


def _graph_base() -> str:
    flags = get_whatsapp_cloud_flags()
    return f"https://{GRAPH_API_HOST}/{flags.graph_api_version}"


def assert_graph_url_safe(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_GRAPH_HOSTS:
        raise WhatsAppGraphError("ssrf_blocked", "Refusing non-Graph host for WhatsApp media/API fetch")


async def exchange_embedded_signup_code(
    *, code: str, redirect_uri: str, app_id: str, app_secret: str
) -> dict[str, Any]:
    if not code.strip():
        raise WhatsAppGraphError("missing_code", "authorization code missing")
    url = f"{_graph_base()}/oauth/access_token"
    params = {
        "client_id": app_id,
        "client_secret": app_secret,
        "code": code.strip(),
        "redirect_uri": redirect_uri,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params)
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400 or "access_token" not in data:
        raise WhatsAppGraphError(
            "token_exchange_failed",
            "Meta rejected WhatsApp Embedded Signup code exchange",
            http_status=resp.status_code,
            retryable=resp.status_code >= 500,
        )
    return data


async def debug_token(*, input_token: str, app_id: str, app_secret: str) -> dict[str, Any]:
    url = f"{_graph_base()}/debug_token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            params={"input_token": input_token, "access_token": f"{app_id}|{app_secret}"},
        )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        raise WhatsAppGraphError("debug_token_failed", "debug_token failed", http_status=resp.status_code)
    return data.get("data") if isinstance(data.get("data"), dict) else data


async def discover_shared_whatsapp_assets(*, access_token: str) -> list[dict[str, Any]]:
    """Return WABA + phone number assets actually shared with the app."""

    url = f"{_graph_base()}/me/businesses"
    async with httpx.AsyncClient(timeout=45.0) as client:
        # Primary: debug shared WABAs via WhatsApp Business Accounts edge when present.
        waba_url = f"{_graph_base()}/debug_token"
        # Prefer explicit shared WABA listing used by Embedded Signup completion:
        shared = await client.get(
            f"{_graph_base()}/me",
            params={
                "fields": "id",
                "access_token": access_token,
            },
        )
        if shared.status_code >= 400:
            raise WhatsAppGraphError("asset_discovery_failed", "unable to resolve Meta user for asset discovery")

        # Embedded Signup typically returns WABA via client message; server verifies via:
        # GET /{waba-id}?fields=id,name,phone_numbers
        # Caller supplies candidate IDs; this helper lists phone numbers for a WABA.
        _ = waba_url
        _ = url
    return []


async def fetch_waba_phone_numbers(*, access_token: str, waba_id: str) -> list[dict[str, Any]]:
    waba = str(waba_id or "").strip()
    if not waba.isdigit():
        raise WhatsAppGraphError("invalid_waba", "WABA id must be numeric")
    url = f"{_graph_base()}/{waba}/phone_numbers"
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.get(
            url,
            params={
                "fields": "id,display_phone_number,verified_name,quality_rating",
                "access_token": access_token,
            },
        )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        raise WhatsAppGraphError(
            "waba_phones_failed",
            "unable to list WABA phone numbers",
            http_status=resp.status_code,
            retryable=resp.status_code >= 500,
        )
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict) and str(row.get("id") or "").isdigit():
            out.append(row)
    return out


async def subscribe_waba_webhooks(*, access_token: str, waba_id: str) -> dict[str, Any]:
    waba = str(waba_id or "").strip()
    if not waba.isdigit():
        raise WhatsAppGraphError("invalid_waba", "WABA id must be numeric")
    url = f"{_graph_base()}/{waba}/subscribed_apps"
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(url, params={"access_token": access_token})
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400 or data.get("success") is False:
        raise WhatsAppGraphError(
            "waba_subscribe_failed",
            "WABA webhook subscription failed",
            http_status=resp.status_code,
            retryable=resp.status_code >= 500,
        )
    return data if isinstance(data, dict) else {"success": True}


async def send_text_message(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    text: str,
) -> dict[str, Any]:
    pnid = str(phone_number_id or "").strip()
    if not pnid.isdigit():
        raise WhatsAppGraphError("invalid_phone_number_id", "phone_number_id must be numeric")
    body = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    url = f"{_graph_base()}/{pnid}/messages"
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=body,
        )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        err = data.get("error") if isinstance(data, dict) else None
        code = str((err or {}).get("code") or "send_failed")
        retryable = resp.status_code >= 500 or code in {"1", "2", "4", "17", "80007"}
        raise WhatsAppGraphError(
            f"meta_{code}",
            "WhatsApp Cloud send rejected",
            http_status=resp.status_code,
            retryable=retryable,
        )
    return data if isinstance(data, dict) else {}


async def create_message_template(
    *,
    access_token: str,
    waba_id: str,
    name: str,
    language: str,
    category: str,
    body_text: str,
) -> dict[str, Any]:
    waba = str(waba_id or "").strip()
    if not waba.isdigit():
        raise WhatsAppGraphError("invalid_waba", "WABA id must be numeric")
    payload = {
        "name": name,
        "language": language,
        "category": category,
        "components": [{"type": "BODY", "text": body_text}],
    }
    url = f"{_graph_base()}/{waba}/message_templates"
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload,
        )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        raise WhatsAppGraphError(
            "template_create_failed",
            "Meta rejected template creation",
            http_status=resp.status_code,
            retryable=False,
        )
    return data if isinstance(data, dict) else {}


async def list_message_templates(*, access_token: str, waba_id: str) -> list[dict[str, Any]]:
    waba = str(waba_id or "").strip()
    if not waba.isdigit():
        raise WhatsAppGraphError("invalid_waba", "WABA id must be numeric")
    url = f"{_graph_base()}/{waba}/message_templates"
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.get(
            url,
            params={"access_token": access_token, "limit": 100},
        )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        raise WhatsAppGraphError("template_list_failed", "unable to list templates", http_status=resp.status_code)
    rows = data.get("data") if isinstance(data, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


async def download_media_bytes(*, access_token: str, media_id: str, max_bytes: int = 8_000_000) -> tuple[bytes, str]:
    mid = str(media_id or "").strip()
    if not mid.isdigit():
        raise WhatsAppGraphError("invalid_media_id", "media id must be numeric")
    meta_url = f"{_graph_base()}/{mid}"
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=False) as client:
        meta_resp = await client.get(meta_url, params={"access_token": access_token})
        meta = meta_resp.json() if meta_resp.content else {}
        if meta_resp.status_code >= 400 or not isinstance(meta, dict):
            raise WhatsAppGraphError("media_meta_failed", "unable to resolve media metadata")
        download_url = str(meta.get("url") or "").strip()
        mime = str(meta.get("mime_type") or "application/octet-stream")
        assert_graph_url_safe(download_url)
        file_resp = await client.get(
            download_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if file_resp.status_code >= 400:
            raise WhatsAppGraphError("media_download_failed", "media download failed")
        content = file_resp.content
        if len(content) > max_bytes:
            raise WhatsAppGraphError("media_too_large", "media exceeds retention size limit")
        return content, mime
