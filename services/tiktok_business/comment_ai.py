"""Run existing Customer Reply V10 on TikTok comments, then publish via official API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from db.session import whatsapp_session
from services.cm.actions import comments_action_enabled
from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment


def ai_generation_blocked(tenant_id: str) -> bool:
    from services.membership.generative_gate import generative_ai_blocked

    return generative_ai_blocked(tenant_id)
from services.tiktok_business.comment_context import tiktok_video_source
from services.tiktok_business.comment_publish import create_comment_reply
from services.tiktok_business.errors import TikTokApiError
from services.tiktok_business.oauth import ensure_fresh_token
from services.tiktok_business.post_context import resolve_tiktok_post_context
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_content import TikTokContentRepository
from services.tiktok_business.scopes import comments_manage_ready

MAX_ATTEMPTS = 5


def _settle_comment_send(
    *,
    tenant_id: str,
    comment_id: str,
    accepted: bool,
    provider_message_id: str = "",
    extra_ids: tuple[str, ...] | list[str] = (),
) -> None:
    from services.customer_ai.billing import settle_after_send

    settle_after_send(
        tenant_id=tenant_id,
        operation_id=comment_id,
        accepted=accepted,
        channel="tiktok_comment",
        provider_message_id=provider_message_id,
        extra_ids=extra_ids,
    )


def _log_usage(
    *,
    tenant_id: str,
    comment_id: str,
    outcome: str,
    model: str = "",
    tokens: int = 0,
    cost: float = 0.0,
    diagnostics: dict[str, Any] | None = None,
) -> None:
    try:
        from services.interaction_flow_logger import log_interaction

        extra = {"tenant_id": tenant_id}
        if diagnostics:
            extra.update({k: v for k, v in diagnostics.items() if k not in {"access_token", "refresh_token"}})
        log_interaction(
            user_id=f"tiktok:{comment_id}",
            user_message="[redacted]",
            bot_to_user="[redacted]",
            source="tiktok_comment",
            channel="tiktok_comment",
            conversation_id=comment_id,
            handler_path="tiktok_business.comment_ai",
            outcome=outcome,
            model=model or None,
            tokens=tokens or None,
            cost_usd=cost or None,
            cm_diagnostics=extra,
        )
    except Exception:
        pass


async def process_tiktok_comment_ai(
    *, tenant_id: str, connection_id: str, comment_id: str, item_id: str
) -> dict[str, Any]:
    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        content = TikTokContentRepository(session)
        connection = repo.get_connection(connection_id, tenant_id=tenant_id)
        if connection is None:
            return {"skipped": True, "reason": "missing_connection"}
        comment = content.claim_comment_for_ai(tenant_id=tenant_id, comment_id=comment_id)
        if comment is None:
            return {"skipped": True, "reason": "duplicate_or_missing"}
        job, created = content.get_or_create_reply_job(
            tenant_id=tenant_id, connection_id=connection_id, comment_id=comment_id
        )
        if not created and job.delivery_status in {"sent", "skipped"}:
            session.commit()
            return {"skipped": True, "reason": "already_handled"}
        automation = comments_action_enabled(tenant_id, "tiktok")
        job.automation_on = automation
        if not automation:
            job.delivery_status = "skipped"
            job.last_error = "tenant_comment_automation_off"
            content.mark_comment_ai_processed(tenant_id=tenant_id, comment_id=comment_id)
            session.commit()
            _log_usage(tenant_id=tenant_id, comment_id=comment_id, outcome="skipped")
            return {"skipped": True, "reason": "automation_off"}
        if not comments_manage_ready(connection.granted_scopes):
            job.delivery_status = "skipped"
            job.last_error = "missing_manage_comment_scope"
            content.mark_comment_ai_processed(tenant_id=tenant_id, comment_id=comment_id)
            session.commit()
            return {"skipped": True, "reason": "permission_required"}
        if ai_generation_blocked(tenant_id):
            from services.membership.generative_gate import generative_block_reason

            blocked = generative_block_reason(tenant_id) or "insufficient_credits"
            job.delivery_status = "failed"
            job.last_error = blocked
            session.commit()
            _log_usage(tenant_id=tenant_id, comment_id=comment_id, outcome=blocked)
            return {"skipped": True, "reason": blocked}
        text = comment.text
        video_id = item_id or comment.video_item_id
        author = str(comment.author_user_id or comment.author_username or "")
        parent_text = ""
        parent_id = str(comment.parent_comment_id or "").strip()
        if parent_id:
            parent = content.get_comment(tenant_id=tenant_id, comment_id=parent_id)
            if parent is not None:
                parent_text = str(parent.text or "")
        media = content.get_media(tenant_id=tenant_id, item_id=video_id)
        stored_caption = str(getattr(media, "caption", "") or "") if media else ""
        stored_thumb = str(getattr(media, "thumbnail_url", "") or "") if media else ""
        stored_video = tiktok_video_source(media) if media else ""
        token = await ensure_fresh_token(repo, connection)
        open_id = connection.open_id
        session.commit()

    resolved = await resolve_tiktok_post_context(
        tenant_id=tenant_id,
        connection_id=connection_id,
        comment_text=text,
        comment_id=comment_id,
        video_id=video_id,
        account_token=token,
        open_id=open_id,
        stored_caption=stored_caption,
        stored_thumbnail=stored_thumb,
        stored_video_url=stored_video,
    )
    comment_ctx = dict(resolved.get("comment_context") or {})
    comment_ctx.setdefault("conversation_id", f"comment:{tenant_id}:tiktok_comment:{video_id or comment_id}")
    thread_id = str(comment_ctx.get("conversation_id") or "")
    caption = str(resolved.get("caption") or stored_caption or "")
    ctx_diag = {
        "context_level": resolved.get("context_level"),
        "reason_code": (resolved.get("diagnostics") or {}).get("reason_code"),
        "media_refresh_attempted": (resolved.get("diagnostics") or {}).get("media_refresh_attempted"),
        "frame_count": comment_ctx.get("frame_count"),
        "transcript_chars": len(str(comment_ctx.get("video_transcript") or "")),
    }
    outcome = await run_customer_reply_v2_comment(
        tenant_id=tenant_id,
        comment_text=text,
        channel="tiktok_comment",
        comments_enabled=True,
        comment_id=comment_id,
        post_id=video_id,
        caption=caption,
        parent_comment=parent_text,
        media_type="video",
        comment_context=comment_ctx,
        provider_sender_id=author or comment_id,
    )
    from services.customer_ai.comments.destinations import destinations_from_outcome, public_text_for_channel

    plan = destinations_from_outcome(outcome)
    reply_text = public_text_for_channel(plan, private_send_possible=False)
    model = str((getattr(outcome, "metadata", None) or {}).get("model") or "")
    tokens = int((getattr(outcome, "metadata", None) or {}).get("tokens") or 0)
    cost = float((getattr(outcome, "metadata", None) or {}).get("cost_usd") or 0)
    reason = str(getattr(outcome, "reason", None) or "")
    if plan.public_depends_on_private and not reply_text:
        reason = reason or "public_depends_on_unsent_private"
    # V2 sets stop=True when a reply is final (same as Meta comments). Skip only if empty.
    if not reply_text:
        with whatsapp_session() as session:
            content = TikTokContentRepository(session)
            job, _ = content.get_or_create_reply_job(
                tenant_id=tenant_id, connection_id=connection_id, comment_id=comment_id
            )
            job.delivery_status = "skipped"
            job.last_error = (reason or "ai_no_reply")[:255]
            job.model = model[:64]
            content.mark_comment_ai_processed(tenant_id=tenant_id, comment_id=comment_id)
            session.commit()
        _log_usage(
            tenant_id=tenant_id,
            comment_id=comment_id,
            outcome=reason or "ai_no_reply",
            model=model,
            tokens=tokens,
            cost=cost,
            diagnostics=ctx_diag,
        )
        _settle_comment_send(tenant_id=tenant_id, comment_id=comment_id, accepted=False, extra_ids=(thread_id,))
        return {"skipped": True, "reason": reason or "ai_no_reply"}

    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        content = TikTokContentRepository(session)
        connection = repo.get_connection(connection_id, tenant_id=tenant_id)
        if connection is None:
            _settle_comment_send(tenant_id=tenant_id, comment_id=comment_id, accepted=False, extra_ids=(thread_id,))
            return {"skipped": True, "reason": "missing_connection"}
        token = await ensure_fresh_token(repo, connection)
        job, _ = content.get_or_create_reply_job(
            tenant_id=tenant_id, connection_id=connection_id, comment_id=comment_id
        )
        job.reply_text = reply_text[:8000]
        job.delivery_status = "sending"
        job.attempt_count = int(job.attempt_count or 0) + 1
        job.model = model[:64]
        job.tokens = tokens
        job.cost_usd = f"{cost:.6f}" if cost else ""
        session.commit()
        open_id = connection.open_id

    try:
        published = await create_comment_reply(
            access_token=token,
            business_id=open_id,
            video_id=video_id,
            comment_id=comment_id,
            text=reply_text,
        )
    except TikTokApiError as exc:
        retrying = False
        with whatsapp_session() as session:
            content = TikTokContentRepository(session)
            job, _ = content.get_or_create_reply_job(
                tenant_id=tenant_id, connection_id=connection_id, comment_id=comment_id
            )
            job.tiktok_request_id = exc.request_id[:128]
            job.last_error = exc.message[:255]
            if exc.retryable and int(job.attempt_count or 0) < MAX_ATTEMPTS:
                retrying = True
                job.delivery_status = "retrying"
                job.next_retry_at = datetime.now(UTC) + timedelta(seconds=min(300, 8 * (2 ** int(job.attempt_count))))
                content.release_comment_ai_claim(tenant_id=tenant_id, comment_id=comment_id)
            else:
                job.delivery_status = "failed"
            session.commit()
        _log_usage(
            tenant_id=tenant_id,
            comment_id=comment_id,
            outcome="retrying" if retrying else "failed",
            model=model,
            tokens=tokens,
            cost=cost,
            diagnostics=ctx_diag,
        )
        if retrying:
            raise
        _settle_comment_send(tenant_id=tenant_id, comment_id=comment_id, accepted=False, extra_ids=(thread_id,))
        return {"ok": False, "reason": "publish_failed", "request_id": exc.request_id}

    with whatsapp_session() as session:
        content = TikTokContentRepository(session)
        job, _ = content.get_or_create_reply_job(
            tenant_id=tenant_id, connection_id=connection_id, comment_id=comment_id
        )
        job.delivery_status = "sent"
        job.tiktok_request_id = str(published.get("request_id") or "")[:128]
        job.tiktok_reply_id = str(published.get("comment_id") or published.get("reply_id") or "")[:64]
        content.mark_comment_ai_processed(tenant_id=tenant_id, comment_id=comment_id)
        session.commit()
    _settle_comment_send(
        tenant_id=tenant_id,
        comment_id=comment_id,
        accepted=True,
        provider_message_id=str(published.get("comment_id") or published.get("reply_id") or ""),
        extra_ids=(thread_id,),
    )
    _log_usage(
        tenant_id=tenant_id,
        comment_id=comment_id,
        outcome="ok",
        model=model,
        tokens=tokens,
        cost=cost,
        diagnostics=ctx_diag,
    )
    return {"ok": True, "request_id": str(published.get("request_id") or "")}
