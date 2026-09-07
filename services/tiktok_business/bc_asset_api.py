"""Official Business Center Asset + advertiser list reads. Advertiser token only."""

from __future__ import annotations

from typing import Any

from services.tiktok_business.ads_config import get_tiktok_ads_settings
from services.tiktok_business.capabilities import TOKEN_KIND_ADVERTISER, classify_tiktok_error
from services.tiktok_business.errors import TikTokApiError, TikTokBusinessError
from services.tiktok_business.http_client import tiktok_request
from services.tiktok_business.token_guard import assert_advertiser_token


def _as_rows(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _require_advertiser(token_kind: str) -> None:
    if str(token_kind or "").strip() != TOKEN_KIND_ADVERTISER:
        raise TikTokBusinessError(
            "Refusing to send an account-holder token to Business Center Asset.",
            code="token_type_mismatch",
            http_status=400,
        )


async def advertiser_get(*, access_token: str, token_kind: str) -> dict[str, Any]:
    _require_advertiser(token_kind)
    assert_advertiser_token(path="/oauth2/advertiser/get/", token_kind=token_kind)
    settings = get_tiktok_ads_settings()
    payload = await tiktok_request(
        method="GET",
        path="/oauth2/advertiser/get/",
        access_token=access_token,
        params={"app_id": settings.app_id, "secret": settings.secret},
    )
    rows = _as_rows(payload, "list", "advertiser_list")
    advertisers = []
    for row in rows:
        advertiser_id = str(row.get("advertiser_id") or "").strip()
        if advertiser_id:
            advertisers.append(
                {
                    "advertiser_id": advertiser_id,
                    "advertiser_name": str(row.get("advertiser_name") or row.get("name") or "").strip(),
                }
            )
    return {"advertisers": advertisers}


async def bc_get(*, access_token: str, token_kind: str) -> dict[str, Any]:
    _require_advertiser(token_kind)
    assert_advertiser_token(path="/bc/get/", token_kind=token_kind)
    payload = await tiktok_request(method="GET", path="/bc/get/", access_token=access_token)
    rows = _as_rows(payload, "list", "bc_info_list")
    centers = []
    for row in rows:
        bc_id = str(row.get("bc_id") or "").strip()
        if bc_id:
            centers.append({"bc_id": bc_id, "name": str(row.get("name") or row.get("bc_name") or "").strip()})
    return {"business_centers": centers}


async def bc_asset_get(*, access_token: str, token_kind: str, bc_id: str) -> dict[str, Any]:
    _require_advertiser(token_kind)
    assert_advertiser_token(path="/bc/asset/get/", token_kind=token_kind)
    payload = await tiktok_request(
        method="GET",
        path="/bc/asset/get/",
        access_token=access_token,
        params={"bc_id": bc_id, "asset_type": "ADVERTISER"},
    )
    rows = _as_rows(payload, "list", "asset_list")
    assets = []
    for row in rows:
        asset_id = str(row.get("asset_id") or row.get("advertiser_id") or "").strip()
        if asset_id:
            assets.append(
                {
                    "advertiser_id": asset_id,
                    "advertiser_name": str(row.get("asset_name") or row.get("advertiser_name") or "").strip(),
                }
            )
    return {"advertisers": assets}


def bc_error_reason(exc: TikTokApiError) -> str:
    return classify_tiktok_error(tiktok_code=exc.tiktok_code, message=exc.message)
