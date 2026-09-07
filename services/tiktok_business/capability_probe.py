"""Cached safe reads for Query Identity + Business Center Asset. Never hammer unapproved apps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from services.tiktok_business.ads_config import MANUAL_REFRESH_MIN_SECONDS, PROBE_COOLDOWN_SECONDS
from services.tiktok_business.bc_asset_api import advertiser_get, bc_asset_get, bc_error_reason, bc_get
from services.tiktok_business.capabilities import (
    TERMINAL_COOLDOWN_REASONS,
    TOKEN_KIND_ADVERTISER,
    empty_capabilities,
    user_status_for,
)
from services.tiktok_business.errors import TikTokApiError, TikTokBusinessError
from services.tiktok_business.identity_api import identity_error_reason, identity_get, match_identity_to_account
from services.tiktok_business.repository_enhanced import TikTokEnhancedRepository
from services.tiktok_business.scopes import comments_manage_ready, comments_read_ready
from services.tiktok_business.token_guard import assert_advertiser_token


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def cooldown_active(binding: Any, *, force: bool = False) -> bool:
    if force:
        return False
    until = _aware(getattr(binding, "probe_cooldown_until", None))
    return until is not None and until > _utcnow()


def _cooldown_for(reason: str) -> datetime | None:
    now = _utcnow()
    if reason in TERMINAL_COOLDOWN_REASONS:
        return now + timedelta(seconds=PROBE_COOLDOWN_SECONDS)
    if reason == "rate_limited":
        return now + timedelta(seconds=MANUAL_REFRESH_MIN_SECONDS)
    if reason in {"api_error", "missing_advertiser_binding", "identity_not_authorized"}:
        return now + timedelta(seconds=MANUAL_REFRESH_MIN_SECONDS)
    return None


def account_capabilities(*, granted: Any, caption: bool = False, thumbnail: bool = False) -> dict[str, bool]:
    caps = empty_capabilities()
    caps["account_basic"] = True
    caps["video_list"] = True
    caps["comments_read"] = comments_read_ready(granted)
    caps["comments_manage"] = comments_manage_ready(granted)
    caps["caption_available"] = caption
    caps["thumbnail_available"] = thumbnail
    return caps


def _finish(
    repo: TikTokEnhancedRepository,
    binding: Any,
    *,
    reason: str,
    caps: dict[str, bool],
    advertiser_id: str = "",
    bc_id: str = "",
    identity_id: str = "",
    identity_type: str = "",
    identity_authorized_bc_id: str = "",
) -> dict[str, Any]:
    status = user_status_for(
        reason=reason,
        identity_id=identity_id,
        media_available=bool(caps.get("official_video_media_available")),
    )
    if reason == "permission_not_approved":
        status = "waiting_for_permission"
    repo.apply_probe(
        binding,
        status=status,
        reason_code=reason,
        capabilities=caps,
        advertiser_id=advertiser_id,
        bc_id=bc_id,
        identity_id=identity_id,
        identity_type=identity_type,
        identity_authorized_bc_id=identity_authorized_bc_id,
        cooldown_until=_cooldown_for(reason),
    )
    return {
        "status": status,
        "reason_code": reason,
        "capabilities": caps,
        "advertiser_id": advertiser_id,
        "bc_id": bc_id,
        "identity_id": identity_id,
        "identity_type": identity_type,
        "identity_authorized_bc_id": identity_authorized_bc_id,
        "probed": True,
    }


async def probe_enhanced_capabilities(
    *,
    repo: TikTokEnhancedRepository,
    tenant_id: str,
    connection_id: str,
    username: str = "",
    display_name: str = "",
    granted_scopes: Any = None,
    force: bool = False,
) -> dict[str, Any]:
    binding = repo.get_or_create_binding(tenant_id=tenant_id, connection_id=connection_id)
    caps = account_capabilities(granted=granted_scopes)
    opened = repo.open_advertiser_tokens(tenant_id=tenant_id, connection_id=connection_id)
    if opened is None:
        if cooldown_active(binding) and binding.reason_code in TERMINAL_COOLDOWN_REASONS:
            return {
                "status": binding.status,
                "reason_code": binding.reason_code,
                "capabilities": dict(binding.capabilities or caps),
                "probed": False,
                "cached": True,
            }
        return _finish(repo, binding, reason="authorization_required", caps=caps)

    if cooldown_active(binding, force=force) and binding.reason_code in TERMINAL_COOLDOWN_REASONS:
        return {
            "status": binding.status,
            "reason_code": binding.reason_code,
            "capabilities": dict(binding.capabilities or caps),
            "probed": False,
            "cached": True,
        }

    token = str(opened.get("access_token") or "")
    token_kind = str(opened.get("token_kind") or TOKEN_KIND_ADVERTISER)
    try:
        assert_advertiser_token(path="/oauth2/advertiser/get/", token_kind=token_kind)
        advertisers = await advertiser_get(access_token=token, token_kind=token_kind)
    except TikTokApiError as exc:
        return _finish(repo, binding, reason=bc_error_reason(exc), caps=caps)
    except TikTokBusinessError as exc:
        reason = exc.code if exc.code == "token_type_mismatch" else "api_error"
        return _finish(repo, binding, reason=reason, caps=caps)

    advertiser_rows = list(advertisers.get("advertisers") or [])
    bc_id = ""
    try:
        centers = await bc_get(access_token=token, token_kind=token_kind)
        rows = list(centers.get("business_centers") or [])
        if rows:
            bc_id = str(rows[0].get("bc_id") or "")
            caps["business_center_asset"] = True
            if not advertiser_rows and bc_id:
                assets = await bc_asset_get(access_token=token, token_kind=token_kind, bc_id=bc_id)
                advertiser_rows = list(assets.get("advertisers") or [])
    except TikTokApiError as exc:
        bc_reason = bc_error_reason(exc)
        if bc_reason == "permission_not_approved":
            caps["business_center_asset"] = False
        elif not advertiser_rows:
            return _finish(repo, binding, reason=bc_reason, caps=caps, bc_id=bc_id)

    if not advertiser_rows:
        return _finish(repo, binding, reason="missing_advertiser_binding", caps=caps, bc_id=bc_id)

    advertiser_id = str(advertiser_rows[0].get("advertiser_id") or "")
    try:
        identity_payload = await identity_get(access_token=token, token_kind=token_kind, advertiser_id=advertiser_id)
    except TikTokApiError as exc:
        return _finish(
            repo,
            binding,
            reason=identity_error_reason(exc),
            caps=caps,
            advertiser_id=advertiser_id,
            bc_id=bc_id,
        )
    except TikTokBusinessError as exc:
        reason = exc.code if exc.code == "token_type_mismatch" else "api_error"
        return _finish(
            repo,
            binding,
            reason=reason,
            caps=caps,
            advertiser_id=advertiser_id,
            bc_id=bc_id,
        )

    caps["identity_query"] = True
    identities = list(identity_payload.get("identities") or [])
    matched = match_identity_to_account(identities, username=username, display_name=display_name)
    if matched is None:
        return _finish(
            repo,
            binding,
            reason="identity_not_authorized",
            caps=caps,
            advertiser_id=advertiser_id,
            bc_id=bc_id,
        )

    identity_id = str(matched.get("identity_id") or "")
    identity_type = str(matched.get("identity_type") or "")
    identity_bc = str(matched.get("identity_authorized_bc_id") or "")
    caps["identity_video_query"] = True
    return _finish(
        repo,
        binding,
        reason="ok",
        caps=caps,
        advertiser_id=advertiser_id,
        bc_id=bc_id or identity_bc,
        identity_id=identity_id,
        identity_type=identity_type,
        identity_authorized_bc_id=identity_bc,
    )
