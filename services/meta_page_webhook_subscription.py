"""Facebook Page subscribed_apps inspection, mutation, and compensation."""

from __future__ import annotations

import time
from typing import Any

import httpx

from services.meta_app_registry import (
    META_COMMENT_SCOPES,
    MetaAppRegistry,
    MetaAssetBinding,
    get_meta_app_configs,
    get_meta_app_registry,
)
from services.meta_oauth_graph_http import META_GRAPH_BASE_URL, MetaOAuthError, _graph_get, _safe_json
from services.meta_oauth_page_lock import lock_facebook_page_oauth_operation

_PAGE_DM_FIELDS = frozenset({"messages", "messaging_postbacks", "standby"})
_PAGE_COMMENT_FIELD = "feed"
PageWebhookSubscriptionSnapshot = tuple[str, ...] | None


def _page_subscription_context(binding: MetaAssetBinding, registry: MetaAppRegistry) -> tuple[Any, Any]:
    credential = registry.get_credential(binding)
    app = get_meta_app_configs()[binding.app_key]
    if credential.token_app_id != app.app_id or credential.token_profile_id != binding.page_id:
        raise MetaOAuthError("Meta Page subscription credential does not match the binding")
    return credential, app


def _subscription_fields(payload: dict[str, Any], *, app_id: str) -> PageWebhookSubscriptionSnapshot:
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise MetaOAuthError("Meta Page webhook subscription rows could not be verified")
    matching = [row for row in rows if isinstance(row, dict) and str(row.get("id") or "").strip() == app_id]
    if len(matching) > 1:
        raise MetaOAuthError("Meta Page webhook subscription rows are ambiguous")
    if not matching:
        return None
    raw_fields = matching[0].get("subscribed_fields")
    if not isinstance(raw_fields, list):
        raise MetaOAuthError("Meta Page webhook subscription fields could not be verified")
    return tuple(
        sorted(
            {
                str(item.get("name") if isinstance(item, dict) else item).strip().lower()
                for item in raw_fields
                if str(item.get("name") if isinstance(item, dict) else item).strip()
            }
        )
    )


async def _read_page_subscription(
    client: httpx.AsyncClient,
    *,
    page_id: str,
    access_token: str,
    app_id: str,
    step: str,
) -> PageWebhookSubscriptionSnapshot:
    payload = await _graph_get(
        client,
        f"{page_id}/subscribed_apps",
        step=step,
        params={"fields": "id,subscribed_fields"},
        bearer_token=access_token,
    )
    return _subscription_fields(payload, app_id=app_id)


async def inspect_binding_webhook_subscription(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient | None = None,
) -> PageWebhookSubscriptionSnapshot:
    """Capture this app's exact Page subscription before any OAuth mutation."""

    credential, app = _page_subscription_context(binding, registry)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(base_url=f"{META_GRAPH_BASE_URL}/{app.graph_api_version}", timeout=20.0)
    try:
        return await _read_page_subscription(
            http_client,
            page_id=binding.page_id,
            access_token=credential.access_token,
            app_id=app.app_id,
            step="webhook subscription preflight",
        )
    finally:
        if owns_client:
            await http_client.aclose()


async def restore_binding_webhook_subscription(
    binding: MetaAssetBinding,
    snapshot: PageWebhookSubscriptionSnapshot,
    *,
    expected_current: PageWebhookSubscriptionSnapshot,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Restore one Page subscription while holding the shared writer lock."""

    _credential, app = _page_subscription_context(binding, registry)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(base_url=f"{META_GRAPH_BASE_URL}/{app.graph_api_version}", timeout=20.0)
    try:
        async with lock_facebook_page_oauth_operation(
            registry,
            app_key=binding.app_key,
            page_ids=(binding.page_id,),
        ):
            await _restore_binding_webhook_subscription_locked(
                binding,
                snapshot,
                expected_current=expected_current,
                registry=registry,
                client=http_client,
            )
    finally:
        if owns_client:
            await http_client.aclose()


async def _restore_binding_webhook_subscription_locked(
    binding: MetaAssetBinding,
    snapshot: PageWebhookSubscriptionSnapshot,
    *,
    expected_current: PageWebhookSubscriptionSnapshot,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient,
) -> None:
    """Compensate only when the provider still holds this callback's write."""

    credential, app = _page_subscription_context(binding, registry)
    headers = {"Authorization": f"Bearer {credential.access_token}"}
    try:
        current = await _read_page_subscription(
            client,
            page_id=binding.page_id,
            access_token=credential.access_token,
            app_id=app.app_id,
            step="webhook subscription compensation ownership check",
        )
        if current == snapshot:
            return
        if current != expected_current:
            raise MetaOAuthError(
                "Meta Page webhook subscription changed after this callback; refusing stale compensation"
            )
        if snapshot is None:
            response = await client.delete(f"{binding.page_id}/subscribed_apps", headers=headers)
            restored = _safe_json(response, step="webhook subscription compensation")
        else:
            response = await client.post(
                f"{binding.page_id}/subscribed_apps",
                data={"subscribed_fields": ",".join(snapshot)},
                headers=headers,
            )
            restored = _safe_json(response, step="webhook subscription compensation")
        if restored.get("success") is not True:
            raise MetaOAuthError("Meta did not confirm Page webhook subscription compensation")
        verified = await _read_page_subscription(
            client,
            page_id=binding.page_id,
            access_token=credential.access_token,
            app_id=app.app_id,
            step="webhook subscription compensation verification",
        )
        if verified != snapshot:
            raise MetaOAuthError("Meta Page webhook subscription compensation could not be verified")
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Meta webhook subscription compensation request failed") from exc


def desired_binding_webhook_subscription(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry,
) -> tuple[str, ...]:
    """Return the exact provider state written by ``subscribe_binding_webhook``."""

    credential, _app = _page_subscription_context(binding, registry)
    existing = {str(item).strip().lower() for item in (binding.webhook_subscribed_fields or ())}
    desired_fields = set(_PAGE_DM_FIELDS)
    if _PAGE_COMMENT_FIELD in existing or META_COMMENT_SCOPES["facebook"].issubset(credential.scopes):
        desired_fields.add(_PAGE_COMMENT_FIELD)
    return tuple(sorted(desired_fields))


async def subscribe_binding_webhook(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Subscribe and read-after-write verify the Page's exact social fields."""

    if not binding.active:
        raise MetaOAuthError("Only an active binding may subscribe webhooks")
    current_registry = registry or get_meta_app_registry()
    async with lock_facebook_page_oauth_operation(
        current_registry,
        app_key=binding.app_key,
        page_ids=(binding.page_id,),
    ):
        credential, app = _page_subscription_context(binding, current_registry)
        owns_client = client is None
        http_client = client or httpx.AsyncClient(
            base_url=f"{META_GRAPH_BASE_URL}/{app.graph_api_version}", timeout=20.0
        )
        fields = desired_binding_webhook_subscription(binding, registry=current_registry)
        desired_fields = set(fields)
        try:
            response = await http_client.post(
                f"{binding.page_id}/subscribed_apps",
                data={"subscribed_fields": ",".join(fields)},
                headers={"Authorization": f"Bearer {credential.access_token}"},
            )
            posted = _safe_json(response, step="webhook subscription")
            if posted.get("success") is not True:
                raise MetaOAuthError("Meta did not confirm the Page webhook subscription")
            verified_fields = await _read_page_subscription(
                http_client,
                page_id=binding.page_id,
                access_token=credential.access_token,
                app_id=app.app_id,
                step="webhook subscription verification",
            )
            if verified_fields is None or set(verified_fields) != desired_fields:
                raise MetaOAuthError("Meta Page webhook subscription fields do not match the approved state")
            try:
                with current_registry._locked():
                    state = current_registry._read_unlocked()
                    raw = state["bindings"].get(binding.binding_id)
                    if not isinstance(raw, dict):
                        raise MetaOAuthError("Meta binding disappeared while recording webhook readiness")
                    changed = dict(raw)
                    changed.update(
                        webhook_subscribed_fields=list(fields),
                        webhook_subscription_status="ready",
                        webhook_subscription_error="",
                        webhook_subscription_checked_at=time.time(),
                        updated_at=time.time(),
                    )
                    state["bindings"][binding.binding_id] = changed
                    current_registry._write_unlocked(state)
            except MetaOAuthError:
                raise
            except Exception as exc:
                raise MetaOAuthError("Meta Page webhook readiness could not be persisted") from exc
        except httpx.HTTPError as exc:
            raise MetaOAuthError("Meta webhook subscription request failed") from exc
        finally:
            if owns_client:
                await http_client.aclose()
