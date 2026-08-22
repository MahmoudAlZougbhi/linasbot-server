"""App-level Page webhook subscription (include_values required for feed parsing)."""

from __future__ import annotations

import os

import httpx

from services.meta_app_registry import APP_A_KEY, get_meta_app_configs
from services.meta_oauth import MetaOAuthError, _safe_json

APP_PAGE_WEBHOOK_CALLBACK = "https://www.linasaibot.com/webhook/meta-messaging"
APP_PAGE_WEBHOOK_FIELDS = ("feed", "messages", "messaging_postbacks", "standby")

__all__ = ["APP_PAGE_WEBHOOK_CALLBACK", "APP_PAGE_WEBHOOK_FIELDS", "ensure_app_page_webhook_subscription"]


async def ensure_app_page_webhook_subscription(
    *,
    app_key: str = APP_A_KEY,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Idempotently ensure App A's page subscription sends feed values."""

    if app_key != APP_A_KEY:
        raise MetaOAuthError("App page webhook subscription applies to App A only")
    app = get_meta_app_configs()[app_key]
    verify_token = str(os.getenv("META_WEBHOOK_VERIFY_TOKEN") or "").strip()
    if len(verify_token) < 32:
        raise MetaOAuthError("Meta webhook verify token is missing or malformed")
    app_token = f"{app.app_id}|{app.app_secret}"
    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        base_url=f"https://graph.facebook.com/{app.graph_api_version}",
        timeout=20.0,
    )
    try:
        response = await http_client.post(
            f"{app.app_id}/subscriptions",
            data={
                "object": "page",
                "callback_url": APP_PAGE_WEBHOOK_CALLBACK,
                "verify_token": verify_token,
                "fields": ",".join(APP_PAGE_WEBHOOK_FIELDS),
                "include_values": "true",
            },
            headers={"Authorization": f"Bearer {app_token}"},
        )
        result = _safe_json(response, step="app page webhook subscription")
        if result.get("success") is not True:
            raise MetaOAuthError("Meta did not confirm app page webhook subscription")
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Meta app page webhook subscription request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()
