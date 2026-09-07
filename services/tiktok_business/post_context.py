"""Resolve TikTok comment post context. full_video only after official media is processed."""

from __future__ import annotations

from typing import Any

from db.session import whatsapp_session
from services.tiktok_business.ads_oauth import ensure_fresh_advertiser_token
from services.tiktok_business.capabilities import TOKEN_KIND_ADVERTISER, empty_capabilities
from services.tiktok_business.comment_context import build_tiktok_comment_context
from services.tiktok_business.errors import TikTokApiError, TikTokBusinessError
from services.tiktok_business.identity_api import identity_error_reason, identity_video_info
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_enhanced import TikTokEnhancedRepository
from services.tiktok_business.video_source import fetch_tiktok_video_item


def _https(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.startswith("https://") else ""


def _looks_expired(status: str, error: str = "") -> bool:
    blob = f"{status} {error}".lower()
    return any(token in blob for token in ("expired", "x-expires", "http_403", "http_404", "http_410"))


def context_level_for(*, caption: str, thumbnail_url: str, frame_count: int, transcript: str, video_ok: bool) -> str:
    if video_ok and (int(frame_count or 0) > 0 or bool(str(transcript or "").strip())):
        return "full_video"
    if caption and thumbnail_url:
        return "caption_thumbnail"
    if caption:
        return "caption_only"
    return "comment_only"


def _note_for(level: str) -> str:
    if level == "full_video":
        return "You received official video frames and any extracted audio transcript."
    if level == "caption_thumbnail":
        return "You received the caption and cover image only. You did not see or hear the full video."
    if level == "caption_only":
        return "You received the caption only. You did not see the video."
    return "You received the comment text only. You did not see the post."


async def _identity_media(
    *,
    access_token: str,
    advertiser_id: str,
    identity_id: str,
    identity_type: str,
    item_id: str,
) -> dict[str, Any]:
    try:
        return await identity_video_info(
            access_token=access_token,
            token_kind=TOKEN_KIND_ADVERTISER,
            advertiser_id=advertiser_id,
            identity_id=identity_id,
            identity_type=identity_type,
            item_id=item_id,
        )
    except TikTokBusinessError as exc:
        return {"error": exc.code, "media_url": "", "caption": "", "thumbnail_url": ""}
    except TikTokApiError as exc:
        return {"error": identity_error_reason(exc), "media_url": "", "caption": "", "thumbnail_url": ""}


async def resolve_tiktok_post_context(
    *,
    tenant_id: str,
    connection_id: str,
    comment_text: str,
    comment_id: str,
    video_id: str,
    account_token: str,
    open_id: str,
    stored_caption: str = "",
    stored_thumbnail: str = "",
    stored_video_url: str = "",
) -> dict[str, Any]:
    live = await fetch_tiktok_video_item(access_token=account_token, open_id=open_id, video_id=video_id)
    caption = str(live.get("caption") or stored_caption or "").strip()
    thumbnail_url = _https(live.get("thumbnail_url") or stored_thumbnail)
    share_url = _https(live.get("share_url"))
    video_url = _https(live.get("video_url") or stored_video_url)
    diagnostics: dict[str, Any] = {
        "reason_code": "",
        "media_refresh_attempted": False,
        "identity_used": False,
        "official_media_url_present": False,
    }
    identity_ids = {"advertiser_id": "", "identity_id": "", "identity_type": ""}
    caps = empty_capabilities()
    caps["account_basic"] = True
    caps["video_list"] = True
    caps["caption_available"] = bool(caption)
    caps["thumbnail_available"] = bool(thumbnail_url)

    enhanced_ready = False
    advertiser_token = ""
    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        enhanced = TikTokEnhancedRepository(session)
        connection = repo.get_connection(connection_id, tenant_id=tenant_id)
        binding = enhanced.get_binding(tenant_id=tenant_id, connection_id=connection_id)
        if connection is not None and binding is not None:
            caps.update({k: bool(v) for k, v in dict(binding.capabilities or {}).items()})
            identity_ids = {
                "advertiser_id": binding.advertiser_id or "",
                "identity_id": binding.identity_id or "",
                "identity_type": binding.identity_type or "",
            }
            enhanced_ready = bool(
                binding.status in {"active", "limited"}
                and binding.identity_id
                and binding.advertiser_id
                and binding.identity_type
            )
            diagnostics["reason_code"] = binding.reason_code or ""
            if enhanced_ready:
                advertiser_token = (await ensure_fresh_advertiser_token(enhanced, connection)) or ""
        session.commit()

    if enhanced_ready and advertiser_token:
        diagnostics["identity_used"] = True
        info = await _identity_media(
            access_token=advertiser_token,
            advertiser_id=identity_ids["advertiser_id"],
            identity_id=identity_ids["identity_id"],
            identity_type=identity_ids["identity_type"],
            item_id=video_id,
        )
        if info.get("error"):
            diagnostics["reason_code"] = str(info.get("error") or diagnostics["reason_code"])
        else:
            caps["identity_video_query"] = True
            caption = str(info.get("caption") or caption).strip()
            thumbnail_url = _https(info.get("thumbnail_url")) or thumbnail_url
            if _https(info.get("media_url")):
                video_url = _https(info.get("media_url"))
                caps["official_video_media_available"] = True

    official_url = _https(video_url)
    diagnostics["official_media_url_present"] = bool(official_url)
    comment_ctx = await build_tiktok_comment_context(
        tenant_id=tenant_id,
        comment_text=comment_text,
        comment_id=comment_id,
        video_id=video_id,
        caption=caption,
        thumbnail_url=thumbnail_url,
        video_url=official_url,
    )
    if official_url and _looks_expired(
        str(comment_ctx.get("video_status") or ""), str(comment_ctx.get("graph_error") or "")
    ):
        if enhanced_ready and advertiser_token and not diagnostics["media_refresh_attempted"]:
            diagnostics["media_refresh_attempted"] = True
            info = await _identity_media(
                access_token=advertiser_token,
                advertiser_id=identity_ids["advertiser_id"],
                identity_id=identity_ids["identity_id"],
                identity_type=identity_ids["identity_type"],
                item_id=video_id,
            )
            refreshed = _https(info.get("media_url"))
            if refreshed and refreshed != official_url:
                comment_ctx = await build_tiktok_comment_context(
                    tenant_id=tenant_id,
                    comment_text=comment_text,
                    comment_id=comment_id,
                    video_id=video_id,
                    caption=str(info.get("caption") or caption).strip() or caption,
                    thumbnail_url=_https(info.get("thumbnail_url")) or thumbnail_url,
                    video_url=refreshed,
                )
                official_url = refreshed
            else:
                diagnostics["reason_code"] = diagnostics["reason_code"] or "expired_media_url"
                comment_ctx = await build_tiktok_comment_context(
                    tenant_id=tenant_id,
                    comment_text=comment_text,
                    comment_id=comment_id,
                    video_id=video_id,
                    caption=caption,
                    thumbnail_url=thumbnail_url,
                    video_url="",
                )
                official_url = ""

    frames = int(comment_ctx.get("frame_count") or 0)
    transcript = str(comment_ctx.get("video_transcript") or "")
    video_status = str(comment_ctx.get("video_status") or "")
    video_ok = (
        bool(official_url)
        and not _looks_expired(video_status)
        and video_status
        not in {
            "video_fetch_failed",
            "tiktok_official_mp4_missing",
        }
    )
    if frames <= 0 and not transcript:
        video_ok = False
    level = context_level_for(
        caption=caption,
        thumbnail_url=thumbnail_url,
        frame_count=frames,
        transcript=transcript,
        video_ok=video_ok,
    )
    if level == "full_video":
        caps["full_video_context_available"] = True
        caps["official_video_media_available"] = True
    elif official_url and not video_ok:
        diagnostics["reason_code"] = diagnostics["reason_code"] or "expired_media_url"
        comment_ctx["tiktok_raw_video"] = False
        comment_ctx["video_raw_unavailable"] = "tiktok_official_mp4_missing"

    comment_ctx["context_level"] = level
    comment_ctx["source_capabilities"] = caps
    comment_ctx["diagnostics"] = diagnostics
    comment_ctx["tiktok_context_note"] = _note_for(level)
    comment_ctx["share_url"] = share_url
    comment_ctx.update(identity_ids)
    return {
        "comment_context": comment_ctx,
        "caption": caption,
        "thumbnail_url": thumbnail_url,
        "context_level": level,
        "diagnostics": diagnostics,
        "source_capabilities": caps,
    }
