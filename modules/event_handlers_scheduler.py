"""Wire APScheduler jobs for KEEP runtime workers."""

from __future__ import annotations

import asyncio
from typing import Any


async def run_smart_followup_worker_job() -> None:
    from services.scale.durable_event_claim import release_job_lock, try_acquire_job_lock

    if not try_acquire_job_lock("whatsapp_smart_followup_worker", ttl_seconds=55):
        return
    try:
        from services.integrations.whatsapp.smart_followup.worker import process_due_followup_jobs

        result = await process_due_followup_jobs(limit=25)
        processed = int(result.get("processed") or 0)
        if processed:
            print(f"[smart_followup] processed {processed} due job(s)")
    except Exception as e:
        print(f"❌ Error in Smart Follow-Up worker: {e}")
        import traceback

        traceback.print_exc()
    finally:
        release_job_lock("whatsapp_smart_followup_worker")


async def start_smart_messaging_scheduler(app_state: Any) -> Any:
    """Create, start, and attach the AsyncIOScheduler; return it."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        run_smart_followup_worker_job,
        "interval",
        minutes=1,
        id="whatsapp_smart_followup_worker",
        name="WhatsApp Smart Follow-Up Worker",
        replace_existing=True,
    )
    from modules.inbound_event_reconcile_job import run_inbound_event_reconcile_job

    scheduler.add_job(
        run_inbound_event_reconcile_job,
        "interval",
        minutes=1,
        id="inbound_event_reconcile",
        name="Inbound Event Reconcile Watchdog",
        replace_existing=True,
    )
    from modules.meta_data_deletion_reconcile_job import run_meta_data_deletion_reconcile_job

    scheduler.add_job(
        run_meta_data_deletion_reconcile_job,
        "interval",
        minutes=1,
        id="meta_data_deletion_reconcile",
        name="Meta Data Deletion Per-Node Reconcile",
        replace_existing=True,
    )
    from modules.customer_reply_reconcile_job import run_customer_reply_reconcile_job

    scheduler.add_job(
        run_customer_reply_reconcile_job,
        "interval",
        minutes=1,
        id="customer_reply_reconcile",
        name="Customer Reply Reconcile Worker",
        replace_existing=True,
    )
    from modules.web_chat_release_pending_reconcile_job import run_web_chat_release_pending_reconcile_job

    scheduler.add_job(
        run_web_chat_release_pending_reconcile_job,
        "interval",
        minutes=1,
        id="web_chat_release_pending_reconcile",
        name="Web Chat Release Pending Reconcile",
        replace_existing=True,
    )
    from modules.tiktok_webhook_register_job import run_tiktok_comment_webhook_register_job

    scheduler.add_job(
        run_tiktok_comment_webhook_register_job,
        "interval",
        minutes=60,
        id="tiktok_comment_webhook_register",
        name="TikTok Comment Webhook Register",
        replace_existing=True,
    )
    from modules.ha_tenant_config_peer_sync_job import run_ha_tenant_config_peer_sync_job

    scheduler.add_job(
        run_ha_tenant_config_peer_sync_job,
        "interval",
        minutes=2,
        id="ha_tenant_config_peer_sync_tick",
        name="HA Tenant Config Peer Sync Tick",
        replace_existing=True,
    )
    from modules.whatsapp_outbound_retry_job import run_whatsapp_outbound_retry_job

    scheduler.add_job(
        run_whatsapp_outbound_retry_job,
        "interval",
        minutes=1,
        id="whatsapp_outbound_retry",
        name="WhatsApp Outbound Retry",
        replace_existing=True,
    )
    from modules.omnichannel_reconcile_job import run_omnichannel_reconcile_job

    scheduler.add_job(
        run_omnichannel_reconcile_job,
        "interval",
        minutes=1,
        id="omnichannel_reconcile",
        name="Omnichannel Inbound/Outbound Reconcile",
        replace_existing=True,
    )
    from modules.message_reservation_gc_job import run_message_reservation_gc_job

    scheduler.add_job(
        run_message_reservation_gc_job,
        "interval",
        minutes=15,
        id="message_reservation_gc",
        name="Message Reservation GC",
        replace_existing=True,
    )

    scheduler.start()

    asyncio.create_task(run_smart_followup_worker_job())
    asyncio.create_task(run_inbound_event_reconcile_job())
    asyncio.create_task(run_meta_data_deletion_reconcile_job())
    asyncio.create_task(run_customer_reply_reconcile_job())
    asyncio.create_task(run_web_chat_release_pending_reconcile_job())
    asyncio.create_task(run_tiktok_comment_webhook_register_job())
    asyncio.create_task(run_ha_tenant_config_peer_sync_job())
    asyncio.create_task(run_whatsapp_outbound_retry_job())
    asyncio.create_task(run_omnichannel_reconcile_job())

    print("✅ Runtime scheduler started")
    print("📅 Scheduled jobs:")
    print("   - Smart Follow-Up worker: Every 1 minute")
    print("   - Inbound event reconcile: Every 1 minute")
    print("   - Meta data deletion reconcile: Every 1 minute per node")
    print("   - Customer reply reconcile: Every 1 minute")
    print("   - Web Chat release pending reconcile: Every 1 minute")
    print("   - TikTok comment webhook register: Every 60 minutes")
    print("   - WhatsApp outbound retry: Every 1 minute")
    print("   - HA tenant config peer sync: Every 2 minutes")
    print("   - Omnichannel inbound/outbound reconcile: Every 1 minute")
    print("   - Channel inbound: webhook-only (no Graph/API comment poll)")
    print("=" * 60)

    app_state.scheduler = scheduler
    return scheduler
