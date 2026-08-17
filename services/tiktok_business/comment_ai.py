"""Run existing Customer Reply V10 on TikTok comments, then publish via official API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from db.session import whatsapp_session
from services.cm.actions import comments_action_enabled
from services.credit_ai_gate import ai_generation_blocked
from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment
from services.tiktok_business.comment_publish import create_comment_reply
from services.tiktok_business.errors import TikTokApiError
from services.tiktok_business.oauth import ensure_fresh_token
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_content import TikTokContentRepository
from services.tiktok_business.scopes import comments_manage_ready

MAX_ATTEMPTS = 5


def _log_usage(
    *, tenant_id: str, comment_id: str, outcome: str, model: str = "", tokens: int = 0, cost: float = 0.0
) -> None:
    try:
        from services.interaction_flow_logger import log_interaction

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
            cm_diagnostics={"tenant_id": tenant_id},
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
            session.commit()
            _log_usage(tenant_id=tenant_id, comment_id=comment_id, outcome="skipped")
            return {"skipped": True, "reason": "automation_off"}
        if not comments_manage_ready(connection.granted_scopes):
            job.delivery_status = "skipped"
            job.last_error = "missing_manage_comment_scope"
            session.commit()
            return {"skipped": True, "reason": "permission_required"}
        if ai_generation_blocked(tenant_id):
            job.delivery_status = "failed"
            job.last_error = "insufficient_credits"
            session.commit()
            _log_usage(tenant_id=tenant_id, comment_id=comment_id, outcome="insufficient_credits")
            return {"skipped": True, "reason": "insufficient_credits"}
        text = comment.text
        video_id = item_id or comment.video_item_id
        session.commit()

    outcome = await run_customer_reply_v2_comment(
        tenant_id=tenant_id,
        comment_text=text,
        channel="tiktok_comment",
        comments_enabled=True,
        comment_id=comment_id,
        post_id=video_id,
        provider_sender_id=comment_id,
    )
    reply_text = str(getattr(outcome, "reply", None) or "").strip()
    model = str((getattr(outcome, "metadata", None) or {}).get("model") or "")
    tokens = int((getattr(outcome, "metadata", None) or {}).get("tokens") or 0)
    cost = float((getattr(outcome, "metadata", None) or {}).get("cost_usd") or 0)
    reason = str(getattr(outcome, "reason", None) or "")
    if getattr(outcome, "stop", False) or not reply_text:
        with whatsapp_session() as session:
            content = TikTokContentRepository(session)
            job, _ = content.get_or_create_reply_job(
                tenant_id=tenant_id, connection_id=connection_id, comment_id=comment_id
            )
            job.delivery_status = "skipped"
            job.last_error = (reason or "ai_no_reply")[:255]
            job.model = model[:64]
            session.commit()
        _log_usage(
            tenant_id=tenant_id,
            comment_id=comment_id,
            outcome=reason or "ai_no_reply",
            model=model,
            tokens=tokens,
            cost=cost,
        )
        return {"skipped": True, "reason": reason or "ai_no_reply"}

    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        content = TikTokContentRepository(session)
        connection = repo.get_connection(connection_id, tenant_id=tenant_id)
        if connection is None:
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
        with whatsapp_session() as session:
            content = TikTokContentRepository(session)
            job, _ = content.get_or_create_reply_job(
                tenant_id=tenant_id, connection_id=connection_id, comment_id=comment_id
            )
            job.tiktok_request_id = exc.request_id[:128]
            job.last_error = exc.message[:255]
            if exc.retryable and int(job.attempt_count or 0) < MAX_ATTEMPTS:
                job.delivery_status = "retrying"
                job.next_retry_at = datetime.now(UTC) + timedelta(seconds=min(300, 8 * (2 ** int(job.attempt_count))))
            else:
                job.delivery_status = "failed"
            session.commit()
        _log_usage(
            tenant_id=tenant_id,
            comment_id=comment_id,
            outcome="retrying" if exc.retryable else "failed",
            model=model,
            tokens=tokens,
            cost=cost,
        )
        if exc.retryable:
            raise
        return {"ok": False, "reason": "publish_failed", "request_id": exc.request_id}

    with whatsapp_session() as session:
        content = TikTokContentRepository(session)
        job, _ = content.get_or_create_reply_job(
            tenant_id=tenant_id, connection_id=connection_id, comment_id=comment_id
        )
        job.delivery_status = "sent"
        job.tiktok_request_id = str(published.get("request_id") or "")[:128]
        job.tiktok_reply_id = str(published.get("comment_id") or published.get("reply_id") or "")[:64]
        session.commit()
    _log_usage(tenant_id=tenant_id, comment_id=comment_id, outcome="ok", model=model, tokens=tokens, cost=cost)
    return {"ok": True, "request_id": str(published.get("request_id") or "")}
