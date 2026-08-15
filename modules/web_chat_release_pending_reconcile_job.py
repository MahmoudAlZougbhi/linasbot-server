"""Periodic reconcile for durable web-chat RELEASE_PENDING operations."""

from __future__ import annotations

from services.durable_event_claim import release_job_lock, try_acquire_job_lock


async def run_web_chat_release_pending_reconcile_job() -> None:
    if not try_acquire_job_lock("web_chat_release_pending_reconcile", ttl_seconds=55):
        return
    try:
        from db.session import whatsapp_db_configured

        if not whatsapp_db_configured():
            return
        from services.web_chat.operation_release_pending_sweeper import sweep_release_pending_operations

        result = sweep_release_pending_operations(limit=50)
        if result.released or result.pending or result.failed:
            print(
                "[web-chat-release-pending] "
                f"examined={result.examined} released={result.released} "
                f"pending={result.pending} skipped={result.skipped} failed={result.failed}"
            )
    except Exception as exc:
        print(f"[web-chat-release-pending] failed type={type(exc).__name__}")
    finally:
        release_job_lock("web_chat_release_pending_reconcile")
