"""graph.instagram.com subscribed_apps reads and the one allowed write."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
    get_meta_app_configs,
)
from services.meta_instagram_login_config import (
    META_INSTAGRAM_GRAPH_BASE_URL,
    instagram_login_app_id,
    instagram_login_graph_api_version,
)
from services.meta_instagram_login_subscription_telemetry import (
    extract_instagram_subscribed_apps_telemetry,
    log_instagram_subscribed_apps_telemetry,
)
from services.meta_oauth_graph_http import MetaOAuthError, _safe_json

InstagramLoginWebhookSubscriptionSnapshot = tuple[str, ...] | None
# graph.instagram.com may return the IG professional account id in top-level `id`
# when `application` is omitted from `fields`. Always request `application{id}`.
INSTAGRAM_SUBSCRIBED_APPS_READ_FIELDS = "application{id},subscribed_fields"
_runtime_logger = logging.getLogger("uvicorn.error")


class InstagramSubscribedAppsProviderError(MetaOAuthError):
    """Secret-safe provider response classification for one subscribed_apps call."""

    def __init__(self, message: str, *, rate_limited: bool, retryable: bool) -> None:
        super().__init__(message)
        self.rate_limited = rate_limited
        self.retryable = retryable


def raise_classified_provider_error(response: httpx.Response, *, step: str) -> None:
    """Raise a fixed-message error for a non-success provider response."""

    safe = extract_instagram_subscribed_apps_telemetry(response)
    rate_limited = response.status_code == 429 or safe["error_code"] == "613"
    provider_error = bool(safe["error_type"] or safe["error_code"])
    if 200 <= response.status_code < 300 and not provider_error:
        return
    if rate_limited:
        message = "Instagram rate-limited webhook setup (Graph error 613). Do not tap Connect again."
    else:
        message = (
            f"Meta {step} returned an OAuth error"
            if 200 <= response.status_code < 300
            else f"Meta {step} failed with HTTP {response.status_code}"
        )
    raise InstagramSubscribedAppsProviderError(
        message,
        rate_limited=rate_limited,
        retryable=rate_limited or response.status_code >= 500 or safe["is_transient"] == "true",
    )


def expected_instagram_login_subscription_app_ids() -> frozenset[str]:
    """Accept either the Instagram product id or the parent Facebook app id."""

    ids = {instagram_login_app_id()}
    app = get_meta_app_configs().get(APP_A_KEY)
    if app is not None:
        app_id = str(app.app_id or "").strip()
        if app_id:
            ids.add(app_id)
    return frozenset(id_value for id_value in ids if id_value)


def _row_identity_ids(row: dict[str, Any]) -> set[str]:
    """Collect every non-secret id Meta may place on one subscribed_apps row."""

    ids: set[str] = set()
    application = row.get("application")
    if isinstance(application, dict):
        nested_id = str(application.get("id") or "").strip()
        if nested_id:
            ids.add(nested_id)
    top_level_id = str(row.get("id") or "").strip()
    if top_level_id:
        ids.add(top_level_id)
    return ids


def _row_app_ids(row: dict[str, Any]) -> set[str]:
    """Return Meta app ids for one subscribed_apps row.

    Prefer nested ``application.id`` when present. Top-level ``id`` is only used
    when Meta omits ``application`` (legacy rows).
    """

    application = row.get("application")
    if isinstance(application, dict):
        nested_id = str(application.get("id") or "").strip()
        if nested_id:
            return {nested_id}
    raw_id = str(row.get("id") or "").strip()
    return {raw_id} if raw_id else set()


def _normalize_subscribed_field(item: Any) -> str:
    if isinstance(item, dict):
        raw = item.get("name")
        if raw is None:
            raw = item.get("id")
        return str(raw or "").strip().lower()
    return str(item).strip().lower()


def _fields_from_row(row: dict[str, Any]) -> set[str] | None:
    raw_fields = row.get("subscribed_fields")
    if isinstance(raw_fields, list):
        names = {_normalize_subscribed_field(item) for item in raw_fields}
        return {name for name in names if name}
    if isinstance(raw_fields, str):
        return {item.strip().lower() for item in raw_fields.split(",") if item.strip()}
    return None


def _select_matching_subscription_row(matching: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer the Instagram Login app row when the parent Facebook app is also listed."""

    if not matching:
        return None
    ig_id = instagram_login_app_id()
    ig_rows = [row for row in matching if ig_id in _row_app_ids(row)]
    if len(ig_rows) > 1:
        raise MetaOAuthError("Instagram webhook subscription rows are ambiguous")
    if len(ig_rows) == 1:
        return ig_rows[0]
    if len(matching) == 1:
        return matching[0]
    raise MetaOAuthError("Instagram webhook subscription rows are ambiguous")


def _selected_app_kind(row: dict[str, Any]) -> str:
    if instagram_login_app_id() in _row_app_ids(row):
        return "ig_app"
    return "fb_app"


def _row_matches_expected(
    row: dict[str, Any],
    *,
    expected_ids: frozenset[str],
    ig_user_id: str | None,
) -> bool:
    fields = _fields_from_row(row)
    if fields is None:
        return False
    identity_ids = _row_identity_ids(row)
    if identity_ids & expected_ids:
        return True
    return bool(ig_user_id and ig_user_id in identity_ids)


def _row_is_identityless_with_fields(row: dict[str, Any]) -> bool:
    """True when Meta returned webhook fields but omitted every recognizable id."""

    if _fields_from_row(row) is None:
        return False
    return not _row_identity_ids(row)


def _account_scoped_subscription_rows(
    rows: list[Any],
    *,
    expected_ids: frozenset[str],
    ig_user_id: str | None,
) -> list[dict[str, Any]]:
    """Match rows for GET /{ig_user_id}/subscribed_apps.

    Meta sometimes returns one row with ``subscribed_fields`` but omits both
    ``application`` and top-level ``id``. The endpoint is already scoped to one
    professional account, so a sole identityless field-bearing row is trusted.
    Rows that carry an unrecognized id still fail closed.
    """

    matching = [
        row
        for row in rows
        if isinstance(row, dict) and _row_matches_expected(row, expected_ids=expected_ids, ig_user_id=ig_user_id)
    ]
    if matching or not ig_user_id:
        return matching
    field_rows = [row for row in rows if isinstance(row, dict) and _row_is_identityless_with_fields(row)]
    if len(field_rows) == 1:
        return field_rows
    return []


def _row_parse_diag(row: dict[str, Any]) -> str:
    fields = _fields_from_row(row)
    return (
        f"app_dict={int(isinstance(row.get('application'), dict))} "
        f"has_fields={int(fields is not None)} "
        f"field_count={0 if fields is None else len(fields)}"
    )


def parse_subscription_snapshot(
    payload: dict[str, Any],
    *,
    ig_user_id: str | None = None,
) -> InstagramLoginWebhookSubscriptionSnapshot:
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise MetaOAuthError("Instagram webhook subscription rows could not be verified")
    expected_ids = expected_instagram_login_subscription_app_ids()
    matching = _account_scoped_subscription_rows(
        rows,
        expected_ids=expected_ids,
        ig_user_id=ig_user_id,
    )
    selected = _select_matching_subscription_row(matching)
    if selected is None:
        diag = _row_parse_diag(rows[0]) if len(rows) == 1 and isinstance(rows[0], dict) else "row_shape=multi"
        _runtime_logger.info(
            "instagram subscribed_apps parse row_count=%s matched_count=0 selected=none field_count=- %s",
            len(rows),
            diag,
        )
        return None
    fields = _fields_from_row(selected)
    _runtime_logger.info(
        "instagram subscribed_apps parse row_count=%s matched_count=%s selected=%s field_count=%s",
        len(rows),
        len(matching),
        _selected_app_kind(selected),
        "-" if fields is None else len(fields),
    )
    if fields is None:
        raise MetaOAuthError("Instagram webhook subscription fields could not be verified")
    return tuple(sorted(fields))


def instagram_login_subscription_context(
    binding: MetaAssetBinding,
    registry: MetaAppRegistry,
) -> tuple[MetaBindingCredential, str, str]:
    if binding.channel != "instagram" or binding.auth_flow != "instagram_login":
        raise MetaOAuthError("Instagram Login subscription requires a direct Instagram binding")
    ig_user_id = str(binding.asset_id or "").strip()
    if not ig_user_id.isdigit():
        raise MetaOAuthError("Instagram professional account id is invalid")
    credential = registry.get_credential(binding)
    expected_app_id = instagram_login_app_id()
    if credential.token_app_id != expected_app_id:
        raise MetaOAuthError("Instagram Login credential belongs to an unexpected app")
    if credential.token_profile_id != ig_user_id:
        raise MetaOAuthError("Instagram Login credential does not match the professional account")
    app = get_meta_app_configs().get(binding.app_key)
    if app is None or not app.enabled or not app.graph_api_version:
        raise MetaOAuthError("Instagram Login Graph version is unavailable")
    return credential, instagram_login_graph_api_version(), expected_app_id


def subscribed_apps_url(*, ig_user_id: str, graph_api_version: str) -> str:
    return f"{META_INSTAGRAM_GRAPH_BASE_URL}/{graph_api_version}/{ig_user_id}/subscribed_apps"


async def read_instagram_login_subscription(
    *,
    ig_user_id: str,
    access_token: str,
    graph_api_version: str,
    client: httpx.AsyncClient,
    step: str,
    telemetry_stage: str | None = None,
) -> InstagramLoginWebhookSubscriptionSnapshot:
    response = await client.get(
        subscribed_apps_url(ig_user_id=ig_user_id, graph_api_version=graph_api_version),
        params={"fields": INSTAGRAM_SUBSCRIBED_APPS_READ_FIELDS},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if telemetry_stage is not None:
        log_instagram_subscribed_apps_telemetry(response, stage=telemetry_stage)
    raise_classified_provider_error(response, step=step)
    payload = _safe_json(response, step=step)
    return parse_subscription_snapshot(payload, ig_user_id=ig_user_id)


async def inspect_instagram_login_webhook_subscription(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient | None = None,
) -> InstagramLoginWebhookSubscriptionSnapshot:
    """Read this direct Instagram app/account subscription without exposing its token."""

    credential, graph_api_version, _expected_app_id = instagram_login_subscription_context(binding, registry)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=20.0)
    try:
        return await read_instagram_login_subscription(
            ig_user_id=binding.asset_id,
            access_token=credential.access_token,
            graph_api_version=graph_api_version,
            client=http_client,
            step="instagram subscribed_apps disconnect preflight",
        )
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Instagram webhook subscription inspection failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()


async def unsubscribe_instagram_login_webhook_raw(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Delete one direct Instagram subscription after the caller serializes writers."""

    credential, graph_api_version, _expected_app_id = instagram_login_subscription_context(binding, registry)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=20.0)
    try:
        response = await http_client.delete(
            subscribed_apps_url(ig_user_id=binding.asset_id, graph_api_version=graph_api_version),
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        payload = _safe_json(response, step="instagram subscribed_apps disconnect")
        if payload.get("success") is not True:
            raise MetaOAuthError("Instagram webhook disconnect did not return success")
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Instagram webhook disconnect request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()


async def subscribe_instagram_login_fields(
    *,
    ig_user_id: str,
    access_token: str,
    subscribed_fields: tuple[str, ...],
    graph_api_version: str,
    client: httpx.AsyncClient,
) -> None:
    """POST subscribed_fields as the official Instagram Graph query parameter."""

    field_list = ",".join(subscribed_fields)
    response = await client.post(
        f"{subscribed_apps_url(ig_user_id=ig_user_id, graph_api_version=graph_api_version)}"
        f"?subscribed_fields={field_list}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    log_instagram_subscribed_apps_telemetry(response, stage="subscribe", require_success_flag=True)
    raise_classified_provider_error(response, step="instagram subscribed_apps subscribe")
    try:
        payload = _safe_json(response, step="instagram subscribed_apps subscribe")
    except MetaOAuthError as exc:
        raise InstagramSubscribedAppsProviderError(
            "Meta instagram subscribed_apps subscribe returned an invalid acknowledgement",
            rate_limited=False,
            retryable=True,
        ) from exc
    success = payload.get("success")
    if success is False:
        raise MetaOAuthError("Instagram webhook subscription did not return success")
    if success is not True:
        raise InstagramSubscribedAppsProviderError(
            "Meta instagram subscribed_apps subscribe returned an incomplete acknowledgement",
            rate_limited=False,
            retryable=True,
        )


async def restore_instagram_login_webhook_subscription(
    binding: MetaAssetBinding,
    snapshot: InstagramLoginWebhookSubscriptionSnapshot,
    *,
    expected_current: InstagramLoginWebhookSubscriptionSnapshot,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient,
) -> None:
    """Restore direct Instagram provider state only when our delete still owns it."""

    credential, graph_api_version, _expected_app_id = instagram_login_subscription_context(binding, registry)
    current = await read_instagram_login_subscription(
        ig_user_id=binding.asset_id,
        access_token=credential.access_token,
        graph_api_version=graph_api_version,
        client=client,
        step="instagram subscribed_apps compensation ownership check",
    )
    if current == snapshot:
        return
    if current != expected_current:
        raise MetaOAuthError("Instagram webhook subscription changed; refusing stale compensation")
    mutation_error: BaseException | None = None
    try:
        if snapshot is None:
            await unsubscribe_instagram_login_webhook_raw(binding, registry=registry, client=client)
        else:
            await subscribe_instagram_login_fields(
                ig_user_id=binding.asset_id,
                access_token=credential.access_token,
                subscribed_fields=snapshot,
                graph_api_version=graph_api_version,
                client=client,
            )
    except BaseException as exc:  # noqa: BLE001 - verify whether the provider committed before raising
        mutation_error = exc
    try:
        verified = await read_instagram_login_subscription(
            ig_user_id=binding.asset_id,
            access_token=credential.access_token,
            graph_api_version=graph_api_version,
            client=client,
            step="instagram subscribed_apps compensation verification",
        )
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Instagram webhook subscription compensation request failed") from exc
    if verified == snapshot:
        return
    if mutation_error is not None:
        raise mutation_error
    raise MetaOAuthError("Instagram webhook subscription compensation could not be verified")


async def fetch_subscription_fields(
    *,
    ig_user_id: str,
    access_token: str,
    graph_api_version: str,
    client: httpx.AsyncClient,
) -> frozenset[str]:
    snapshot = await read_instagram_login_subscription(
        ig_user_id=ig_user_id,
        access_token=access_token,
        graph_api_version=graph_api_version,
        client=client,
        step="instagram subscribed_apps verify",
        telemetry_stage="verify",
    )
    return frozenset(snapshot or ())
