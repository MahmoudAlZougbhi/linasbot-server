"""Secret-safe HTTP primitives shared by Meta OAuth Graph helpers."""

from __future__ import annotations

from typing import Any, cast

import httpx

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
