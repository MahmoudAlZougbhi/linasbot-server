"""HA-safe TikTok COMMENT webhook registration — one lock across two nodes."""

from __future__ import annotations

from db.session import WhatsAppDatabaseUnavailable, whatsapp_db_configured
from services.durable_event_claim import release_job_lock, try_acquire_job_lock


async def run_tiktok_comment_webhook_register_job() -> None:
    if not try_acquire_job_lock("tiktok_comment_webhook_register", ttl_seconds=55):
        return
    try:
        if not whatsapp_db_configured():
            return
        from services.tiktok_business.config import get_tiktok_settings
        from services.tiktok_business.errors import TikTokApiError
        from services.tiktok_business.webhook_subscription import ensure_comment_webhook_registered

        if not get_tiktok_settings().configured:
            return
        await ensure_comment_webhook_registered()
    except (WhatsAppDatabaseUnavailable, TikTokApiError):
        return
    finally:
        release_job_lock("tiktok_comment_webhook_register")
