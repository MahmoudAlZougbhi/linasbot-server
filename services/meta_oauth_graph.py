"""Meta OAuth Graph helpers and webhook subscribe/unsubscribe (LOC split from meta_oauth)."""

from __future__ import annotations

import time
from typing import Any, Literal, cast

import httpx

from services.meta_app_registry import (
    META_CHANNEL_SCOPES,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaRegistryError,
    get_meta_app_configs,
    get_meta_app_registry,
)

MetaOAuthFlowMode = Literal["facebook", "instagram", "unified"]
META_GRAPH_BASE_URL = "https://graph.facebook.com"


class MetaOAuthError(RuntimeError):
    """OAuth failure whose message never contains a secret or raw Meta response."""


def _safe_json(response: httpx.Response, *, step: str) -> dict[str, Any]:
    if response.status_code < 200 or response.status_code >= 300:
        raise MetaOAuthError(f"Meta {step} failed with HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise MetaOAuthError(f"Meta {step} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise MetaOAuthError(f"Meta {step} returned an invalid response")
    if payload.get("error"):
        raise MetaOAuthError(f"Meta {step} returned an OAuth error")
    return cast(dict[str, Any], payload)


async def _graph_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    step: str,
    params: dict[str, str],
    bearer_token: str = "",
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    try:
        response = await client.get(path, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise MetaOAuthError(f"Meta {step} request failed") from exc
    return _safe_json(response, step=step)


async def _graph_post_form(
    client: httpx.AsyncClient,
    path: str,
    *,
    step: str,
    data: dict[str, str],
    bearer_token: str = "",
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    try:
        response = await client.post(path, data=data, headers=headers)
    except httpx.HTTPError as exc:
        raise MetaOAuthError(f"Meta {step} request failed") from exc
    return _safe_json(response, step=step)


async def _debug_token(
    client: httpx.AsyncClient,
    *,
    token: str,
    app_id: str,
    app_secret: str,
) -> dict[str, Any]:
    payload = await _graph_get(
        client,
        "debug_token",
        step="token inspection",
        params={"input_token": token},
        bearer_token=f"{app_id}|{app_secret}",
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MetaOAuthError("Meta token inspection response is incomplete")
    if not data.get("is_valid") or str(data.get("app_id") or "") != app_id:
        raise MetaOAuthError("Meta token does not belong to the Tech Provider app")
    return cast(dict[str, Any], data)


def _scope_tuple(debug_data: dict[str, Any]) -> tuple[str, ...]:
    scopes = debug_data.get("scopes")
    if not isinstance(scopes, list):
        return ()
    return tuple(sorted({str(scope) for scope in scopes if str(scope).strip()}))


def _granular_targets_are_allowlisted(
    debug_data: dict[str, Any],
    *,
    page_id: str,
    instagram_id: str,
) -> bool:
    granular = debug_data.get("granular_scopes")
    if not isinstance(granular, list):
        return False
    allowed_targets = {page_id}
    if instagram_id:
        allowed_targets.add(instagram_id)
    observed_targets: set[str] = set()
    relevant = [
        item
        for item in granular
        if isinstance(item, dict) and str(item.get("scope") or "") in META_CHANNEL_SCOPES["facebook"]
    ]
    for item in relevant:
        targets = item.get("target_ids")
        if not isinstance(targets, list) or not targets:
            continue
        normalized = {str(value) for value in targets}
        if not normalized.issubset(allowed_targets):
            return False
        observed_targets.update(normalized)
    return page_id in observed_targets


def _eligible_pages(pages: list[dict[str, Any]], *, flow_mode: MetaOAuthFlowMode) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for page in pages:
        page_id = str(page.get("id") or "").strip()
        page_token = str(page.get("access_token") or "").strip()
        instagram = page.get("instagram_business_account")
        if not page_id or not page_token:
            continue
        if flow_mode == "instagram" and not isinstance(instagram, dict):
            continue
        candidates.append(page)
    if not candidates:
        raise MetaOAuthError("No eligible Facebook Page was authorized in Meta Business Login")
    return candidates


async def subscribe_binding_webhook(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Subscribe private-message webhook fields without dropping an existing Page feed field."""

    if not binding.active:
        raise MetaOAuthError("Only an active binding may subscribe webhooks")
    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    app = get_meta_app_configs()[binding.app_key]
    owns_client = client is None
    http_client = client or httpx.AsyncClient(base_url=f"{META_GRAPH_BASE_URL}/{app.graph_api_version}", timeout=20.0)
    # Meta replaces subscribed_fields on POST — preserve feed when Comments already subscribed.
    existing = {str(item).strip().lower() for item in (binding.webhook_subscribed_fields or ())}
    fields = ["messages", "messaging_postbacks"]
    if "feed" in existing:
        fields.append("feed")
    try:
        response = await http_client.post(
            f"{binding.page_id}/subscribed_apps",
            data={"subscribed_fields": ",".join(fields)},
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        _safe_json(response, step="webhook subscription")
        # Persist DM (+ preserved feed) fields on the binding without disconnecting.
        try:
            with current_registry._locked():
                state = current_registry._read_unlocked()
                raw = state["bindings"].get(binding.binding_id)
                if isinstance(raw, dict):
                    changed = dict(raw)
                    prior = [str(item) for item in (changed.get("webhook_subscribed_fields") or [])]
                    changed["webhook_subscribed_fields"] = sorted({*prior, *fields})
                    changed["webhook_subscription_checked_at"] = time.time()
                    changed["updated_at"] = time.time()
                    state["bindings"][binding.binding_id] = changed
                    current_registry._write_unlocked(state)
        except Exception:
            pass
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Meta webhook subscription request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()


def _other_active_binding_shares_page(binding: MetaAssetBinding, registry: MetaAppRegistry) -> bool:
    """True when another active binding still needs this app's Page webhook subscription."""

    page_id = str(binding.page_id or "").strip()
    if not page_id:
        return False
    for other in registry.list_bindings(include_inactive=False, include_superseded=False):
        if other.binding_id == binding.binding_id:
            continue
        if other.app_key != binding.app_key:
            continue
        if str(other.page_id or "").strip() != page_id:
            continue
        if other.auth_flow == "instagram_login":
            continue
        return True
    return False


async def disconnect_binding_webhook(
    binding: MetaAssetBinding,
    *,
    actor_id: str,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """Mark the binding disconnected in-app; best-effort Meta Page unsubscribe.

    Owner disconnect must succeed locally even when Meta Graph cleanup fails
    (expired token, already unsubscribed, transient Graph errors). Instagram Login
    bindings never use Page ``subscribed_apps``. Skip Meta unsubscribe when another
    active non–Instagram-Login binding still shares the same app+Page subscription.
    """

    current_registry = registry or get_meta_app_registry()
    updated = current_registry.set_binding_status(
        binding.binding_id,
        status="disconnected",
        actor_id=actor_id,
        expected_generation=binding.generation,
    )
    should_unsubscribe = (
        binding.auth_flow != "instagram_login"
        and bool(str(binding.page_id or "").strip())
        and not _other_active_binding_shares_page(binding, current_registry)
    )
    if should_unsubscribe:
        try:
            await unsubscribe_binding_webhook(binding, registry=current_registry, client=client)
        except (MetaOAuthError, MetaRegistryError):
            # Local disconnect already committed; Meta cleanup is best-effort only.
            pass
    return updated


async def unsubscribe_binding_webhook(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Remove only this app's Page webhook subscription without mutating registry state."""

    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    app = get_meta_app_configs()[binding.app_key]
    owns_client = client is None
    http_client = client or httpx.AsyncClient(base_url=f"{META_GRAPH_BASE_URL}/{app.graph_api_version}", timeout=20.0)
    try:
        response = await http_client.delete(
            f"{binding.page_id}/subscribed_apps",
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        _safe_json(response, step="webhook disconnect")
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Meta webhook disconnect request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()
