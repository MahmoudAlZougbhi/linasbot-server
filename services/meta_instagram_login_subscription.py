"""Instagram Login per-account webhook subscription via graph.instagram.com."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from services.meta_app_registry import MetaAppRegistry, MetaAssetBinding, MetaBindingCredential, get_meta_app_registry
from services.meta_instagram_login_config import META_INSTAGRAM_GRAPH_BASE_URL, instagram_login_app_id
from services.meta_oauth import MetaOAuthError, _safe_json

_runtime_logger = logging.getLogger("uvicorn.error")

REQUIRED_DM_SUBSCRIPTION_FIELDS = frozenset({"messages", "messaging_postbacks"})
COMMENTS_SUBSCRIPTION_FIELD = "comments"
_SUBSCRIBE_MAX_ATTEMPTS = 3
_SUBSCRIBE_BACKOFF_SECONDS = (0.5, 1.5, 3.0)


@dataclass(frozen=True)
class InstagramLoginSubscriptionState:
    status: str
    subscribed_fields: tuple[str, ...]
    verified_fields: tuple[str, ...]
    error: str = ""

    @property
    def ready_for_dm(self) -> bool:
        return REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(self.verified_fields)

    @property
    def ready_for_comments(self) -> bool:
        return COMMENTS_SUBSCRIPTION_FIELD in self.verified_fields

    def public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "subscribed_fields": list(self.subscribed_fields),
            "verified_fields": list(self.verified_fields),
            "ready_for_dm": self.ready_for_dm,
            "ready_for_comments": self.ready_for_comments,
            "error": self.error,
        }


def subscribed_fields_for_granted_scopes(scopes: tuple[str, ...] | frozenset[str]) -> tuple[str, ...]:
    granted = set(scopes)
    fields = ["messages", "messaging_postbacks"]
    if "instagram_business_manage_comments" in granted:
        fields.append(COMMENTS_SUBSCRIPTION_FIELD)
    return tuple(fields)


def _subscription_status_for_verified(*, verified: frozenset[str], subscribed_fields: tuple[str, ...]) -> str:
    if not REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(verified):
        return "failed"
    if COMMENTS_SUBSCRIPTION_FIELD in subscribed_fields and COMMENTS_SUBSCRIPTION_FIELD not in verified:
        return "partial"
    return "ready"


def _parse_verified_fields(payload: dict[str, Any], *, expected_app_id: str) -> frozenset[str]:
    """Return fields only from the one direct-Instagram app subscription row."""

    rows = payload.get("data")
    matching = [
        row
        for row in (rows if isinstance(rows, list) else [])
        if isinstance(row, dict) and str(row.get("id") or "").strip() == expected_app_id
    ]
    if len(matching) != 1:
        return frozenset()
    subscribed_fields = matching[0].get("subscribed_fields")
    verified: set[str] = set()
    if isinstance(subscribed_fields, list):
        verified.update(str(item).strip() for item in subscribed_fields if str(item).strip())
    if isinstance(subscribed_fields, str):
        verified.update(item.strip() for item in subscribed_fields.split(",") if item.strip())
    return frozenset(verified)


async def _subscribe_once(
    *,
    ig_user_id: str,
    access_token: str,
    subscribed_fields: tuple[str, ...],
    graph_api_version: str,
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        f"{META_INSTAGRAM_GRAPH_BASE_URL}/{graph_api_version}/{ig_user_id}/subscribed_apps",
        data={"subscribed_fields": ",".join(subscribed_fields)},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    payload = _safe_json(response, step="instagram subscribed_apps subscribe")
    if payload.get("success") is not True:
        raise MetaOAuthError("Instagram webhook subscription did not return success")


async def _fetch_subscription_state(
    *,
    ig_user_id: str,
    access_token: str,
    graph_api_version: str,
    expected_app_id: str,
    client: httpx.AsyncClient,
) -> frozenset[str]:
    response = await client.get(
        f"{META_INSTAGRAM_GRAPH_BASE_URL}/{graph_api_version}/{ig_user_id}/subscribed_apps",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    payload = _safe_json(response, step="instagram subscribed_apps verify")
    return _parse_verified_fields(payload, expected_app_id=expected_app_id)


async def ensure_instagram_login_webhook_subscription(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
    *,
    registry: MetaAppRegistry | None = None,
    graph_api_version: str,
    client: httpx.AsyncClient | None = None,
) -> InstagramLoginSubscriptionState:
    """Idempotently subscribe and verify webhook fields for one IG professional account."""

    if binding.auth_flow != "instagram_login":
        raise MetaOAuthError("Webhook subscription applies only to Instagram Login bindings")
    ig_user_id = binding.asset_id.strip()
    if not ig_user_id.isdigit():
        raise MetaOAuthError("Instagram professional account id is invalid")

    subscribed_fields = subscribed_fields_for_granted_scopes(credential.scopes)
    expected_app_id = instagram_login_app_id()
    if credential.token_app_id != expected_app_id:
        raise MetaOAuthError("Instagram Login credential belongs to an unexpected app")
    current_registry = registry or get_meta_app_registry()
    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        base_url=f"{META_INSTAGRAM_GRAPH_BASE_URL}/{graph_api_version}",
        timeout=20.0,
    )
    last_error = ""
    try:
        for attempt, delay in enumerate(_SUBSCRIBE_BACKOFF_SECONDS, start=1):
            try:
                await _subscribe_once(
                    ig_user_id=ig_user_id,
                    access_token=credential.access_token,
                    subscribed_fields=subscribed_fields,
                    graph_api_version=graph_api_version,
                    client=http_client,
                )
                verified = await _fetch_subscription_state(
                    ig_user_id=ig_user_id,
                    access_token=credential.access_token,
                    graph_api_version=graph_api_version,
                    expected_app_id=expected_app_id,
                    client=http_client,
                )
                if REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(verified):
                    status = _subscription_status_for_verified(
                        verified=verified,
                        subscribed_fields=subscribed_fields,
                    )
                    state = InstagramLoginSubscriptionState(
                        status=status,
                        subscribed_fields=subscribed_fields,
                        verified_fields=tuple(sorted(verified)),
                    )
                    current_registry.update_instagram_login_webhook_subscription(
                        binding.binding_id,
                        state=state,
                        actor_id="instagram-login-subscribe",
                    )
                    return state
                last_error = "required_dm_fields_missing_after_verify"
            except (MetaOAuthError, httpx.HTTPError) as exc:
                last_error = type(exc).__name__
                _runtime_logger.warning(
                    "[instagram-login] subscribe_attempt_failed binding=%s attempt=%d reason=%s",
                    binding.binding_id[-8:],
                    attempt,
                    last_error,
                )
            if attempt < _SUBSCRIBE_MAX_ATTEMPTS:
                await asyncio.sleep(delay)

        failed = InstagramLoginSubscriptionState(
            status="failed",
            subscribed_fields=subscribed_fields,
            verified_fields=(),
            error=last_error or "subscription_verify_failed",
        )
        current_registry.update_instagram_login_webhook_subscription(
            binding.binding_id,
            state=failed,
            actor_id="instagram-login-subscribe",
        )
        return failed
    finally:
        if owns_client:
            await http_client.aclose()
