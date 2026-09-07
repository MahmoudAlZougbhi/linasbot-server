"""Official Query Identity reads. Advertiser token only. Never persist preview URLs."""

from __future__ import annotations

import json
from typing import Any

from services.tiktok_business.capabilities import TOKEN_KIND_ADVERTISER, classify_tiktok_error
from services.tiktok_business.errors import TikTokApiError
from services.tiktok_business.http_client import tiktok_request
from services.tiktok_business.token_guard import assert_advertiser_token
from services.tiktok_business.video_source import harvest_official_video_urls


def _https(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.startswith("https://") else ""


def _as_rows(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


async def _advertiser_get(*, path: str, access_token: str, token_kind: str, params: dict[str, Any]) -> dict[str, Any]:
    assert_advertiser_token(path=path, token_kind=token_kind)
    return await tiktok_request(method="GET", path=path, access_token=access_token, params=params)


async def identity_get(*, access_token: str, token_kind: str, advertiser_id: str) -> dict[str, Any]:
    advertiser = str(advertiser_id or "").strip()
    if not advertiser:
        return {"identities": [], "reason": "missing_advertiser_binding"}
    payload = await _advertiser_get(
        path="/identity/get/",
        access_token=access_token,
        token_kind=token_kind,
        params={"advertiser_id": advertiser},
    )
    rows = _as_rows(payload, "identity_list", "list")
    identities = []
    for row in rows:
        identities.append(
            {
                "identity_id": str(row.get("identity_id") or "").strip(),
                "identity_type": str(row.get("identity_type") or "").strip(),
                "display_name": str(row.get("display_name") or row.get("identity_display_name") or "").strip(),
                "username": str(row.get("display_name") or row.get("username") or "").strip(),
                "identity_authorized_bc_id": str(row.get("identity_authorized_bc_id") or "").strip(),
            }
        )
    return {"identities": [row for row in identities if row["identity_id"]], "raw_keys": list(payload.keys())}


async def identity_video_get(
    *,
    access_token: str,
    token_kind: str,
    advertiser_id: str,
    identity_id: str,
    identity_type: str,
) -> dict[str, Any]:
    payload = await _advertiser_get(
        path="/identity/video/get/",
        access_token=access_token,
        token_kind=token_kind,
        params={
            "advertiser_id": advertiser_id,
            "identity_id": identity_id,
            "identity_type": identity_type,
        },
    )
    rows = _as_rows(payload, "video_list", "list")
    item_ids = [str(row.get("item_id") or row.get("video_id") or "").strip() for row in rows]
    return {"item_ids": [item for item in item_ids if item]}


def parse_identity_video_info(payload: dict[str, Any], *, item_id: str) -> dict[str, Any]:
    wanted = str(item_id or "").strip()
    rows = _as_rows(payload, "video_list", "list")
    match = next(
        (row for row in rows if str(row.get("item_id") or row.get("video_id") or "").strip() == wanted),
        rows[0] if rows else {},
    )
    video_info_raw = match.get("video_info")
    video_info = video_info_raw if isinstance(video_info_raw, dict) else {}
    media_url = _https(video_info.get("url")) or ""
    if not media_url:
        harvested = harvest_official_video_urls(match) or harvest_official_video_urls(payload)
        media_url = harvested[0] if harvested else ""
    return {
        "item_id": str(match.get("item_id") or wanted).strip(),
        "caption": str(match.get("text") or match.get("caption") or match.get("video_name") or "").strip(),
        "thumbnail_url": _https(video_info.get("poster_url") or match.get("poster_url")),
        "media_url": media_url,
        "duration": video_info.get("duration") or match.get("duration"),
        "width": video_info.get("width") or match.get("width"),
        "height": video_info.get("height") or match.get("height"),
    }


async def identity_video_info(
    *,
    access_token: str,
    token_kind: str,
    advertiser_id: str,
    identity_id: str,
    identity_type: str,
    item_id: str,
) -> dict[str, Any]:
    wanted = str(item_id or "").strip()
    params: dict[str, Any] = {
        "advertiser_id": advertiser_id,
        "identity_id": identity_id,
        "identity_type": identity_type,
    }
    if wanted:
        params["item_ids"] = json.dumps([wanted], separators=(",", ":"))
    payload = await _advertiser_get(
        path="/identity/video/info/",
        access_token=access_token,
        token_kind=token_kind,
        params=params,
    )
    parsed = parse_identity_video_info(payload, item_id=wanted)
    return parsed


def identity_error_reason(exc: TikTokApiError) -> str:
    return classify_tiktok_error(tiktok_code=exc.tiktok_code, message=exc.message)


def match_identity_to_account(
    identities: list[dict[str, Any]], *, username: str, display_name: str
) -> dict[str, Any] | None:
    handle = str(username or "").strip().lstrip("@").lower()
    name = str(display_name or "").strip().lower()
    for row in identities:
        row_name = str(row.get("username") or row.get("display_name") or "").strip().lstrip("@").lower()
        if handle and row_name == handle:
            return row
        if name and row_name == name:
            return row
    if len(identities) == 1:
        return identities[0]
    return None


def require_advertiser_kind(token_kind: str) -> str:
    kind = str(token_kind or "").strip()
    if kind != TOKEN_KIND_ADVERTISER:
        from services.tiktok_business.errors import TikTokBusinessError

        raise TikTokBusinessError(
            "Refusing to send an account-holder token to Query Identity.",
            code="token_type_mismatch",
            http_status=400,
        )
    return kind
