"""HA-safe TikTok comment sync tick — one lock across two nodes."""

from __future__ import annotations

from db.session import WhatsAppDatabaseUnavailable, whatsapp_db_configured, whatsapp_session
from services.durable_event_claim import release_job_lock, try_acquire_job_lock
from services.job_queue import job_queue
from services.tiktok_business.repository import TikTokRepository


async def run_tiktok_comment_sync_job() -> None:
    if not try_acquire_job_lock("tiktok_comment_sync_tick", ttl_seconds=55):
        return
    try:
        if not whatsapp_db_configured():
            return
        from services.tiktok_business.config import get_tiktok_settings

        if not get_tiktok_settings().configured:
            return
        with whatsapp_session() as session:
            repo = TikTokRepository(session)
            due = repo.list_due_for_sync(limit=20)
            session.commit()
            ids = [(row.tenant_id, row.id) for row in due]
        for tenant_id, connection_id in ids:
            import time

            from services.tiktok_business.config import COMMENT_SYNC_INTERVAL_SECONDS

            bucket = int(time.time() // max(60, COMMENT_SYNC_INTERVAL_SECONDS))
            job_queue.enqueue(
                queue="background",
                job_type="tiktok_comment_sync",
                tenant_id=tenant_id,
                payload={"connection_id": connection_id},
                idempotency_key=f"tiktok_sync:{connection_id}:{bucket}",
            )
    except WhatsAppDatabaseUnavailable:
        return
    finally:
        release_job_lock("tiktok_comment_sync_tick")
