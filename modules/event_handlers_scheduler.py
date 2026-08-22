"""Wire APScheduler jobs for smart messaging (LOC split)."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from modules.event_handlers_monitor_jobs import monitor_smart_messages_job
from services.daily_template_dispatcher import daily_template_dispatcher
from services.smart_messaging import smart_messaging


async def daily_refresh_messages_job() -> None:
    """
    Runs daily to clear stale queue entries while preserving
    long-horizon follow-ups and campaign messages.
    """
    from services.durable_event_claim import release_job_lock, try_acquire_job_lock

    if not try_acquire_job_lock("daily_refresh_messages", ttl_seconds=600):
        print("[smart_scheduler] daily refresh skipped — another instance holds the lock")
        return
    try:
        print("\n" + "=" * 80)
        print("🌅 DAILY MESSAGE REFRESH - Clearing stale queue entries")
        print("=" * 80)

        result = smart_messaging.clear_daily_messages()
        print(f"   🧹 Cleared {result['cleared']} stale messages, kept {result['kept']}")

        print("=" * 80)
        print("✅ DAILY REFRESH COMPLETE")
        print("=" * 80 + "\n")
    except Exception as e:
        print(f"❌ Error in daily refresh job: {e}")
        import traceback

        traceback.print_exc()
    finally:
        release_job_lock("daily_refresh_messages")


async def run_daily_template_dispatcher_job() -> None:
    """
    Minute-level runner that dispatches enabled template jobs
    when local time matches configured HH:MM.
    """
    from services.durable_event_claim import release_job_lock, try_acquire_job_lock

    if not try_acquire_job_lock(
        "daily_template_dispatcher",
        ttl_seconds=max(60, max(1, int(os.getenv("SMART_DISPATCHER_INTERVAL_MINUTES", "5"))) * 60),
    ):
        print("[smart_scheduler] dispatcher tick skipped — another instance holds the lock")
        return
    try:
        dispatch_result = await daily_template_dispatcher.tick()
        run_count = dispatch_result.get("run_count", 0)
        if run_count:
            print(f"📅 Daily template dispatcher ran {run_count} template job(s)")
            for item in dispatch_result.get("jobs_run", []):
                result = item.get("result", {})
                print(
                    f"   - {item.get('template_id')}: "
                    f"{result.get('scheduled_count', 0)} queued "
                    f"(candidates={result.get('total_candidates', 0)})"
                )
    except Exception as e:
        print(f"❌ Error in daily template dispatcher: {e}")
        import traceback

        traceback.print_exc()
    finally:
        release_job_lock("daily_template_dispatcher")


async def run_smart_followup_worker_job() -> None:
    from services.durable_event_claim import release_job_lock, try_acquire_job_lock

    if not try_acquire_job_lock("whatsapp_smart_followup_worker", ttl_seconds=55):
        return
    try:
        from services.whatsapp_cloud.smart_followup.worker import process_due_followup_jobs

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
    dispatcher_interval_minutes = max(
        1,
        int(os.getenv("SMART_DISPATCHER_INTERVAL_MINUTES", "5")),
    )
    monitor_interval_minutes = max(
        1,
        int(os.getenv("SMART_MONITOR_INTERVAL_MINUTES", "5")),
    )

    scheduler.add_job(
        daily_refresh_messages_job,
        "cron",
        hour=0,
        minute=1,
        id="daily_refresh_messages",
        name="Daily Refresh - Clear Stale Scheduled Messages",
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_template_dispatcher_job,
        "interval",
        minutes=dispatcher_interval_minutes,
        id="daily_template_dispatcher",
        name="Daily Template Dispatcher (Config-Driven)",
        replace_existing=True,
    )
    scheduler.add_job(
        monitor_smart_messages_job,
        "interval",
        minutes=monitor_interval_minutes,
        id="monitor_smart_messages",
        name="Monitor Smart Messaging Scheduled Messages",
        replace_existing=True,
    )
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
    from modules.tiktok_sync_job import run_tiktok_comment_sync_job

    scheduler.add_job(
        run_tiktok_comment_sync_job,
        "interval",
        minutes=1,
        id="tiktok_comment_sync_tick",
        name="TikTok Comment Sync Tick",
        replace_existing=True,
    )
    from modules.meta_social_comment_sync_job import run_meta_social_comment_sync_job

    scheduler.add_job(
        run_meta_social_comment_sync_job,
        "interval",
        minutes=1,
        id="meta_social_comment_sync_tick",
        name="Meta Social Comment Sync Tick",
        replace_existing=True,
    )

    scheduler.start()

    print("\n🚀 Running initial daily template dispatcher check...")
    asyncio.create_task(run_daily_template_dispatcher_job())
    print("✅ Initial dispatcher check queued")
    asyncio.create_task(run_smart_followup_worker_job())
    asyncio.create_task(run_inbound_event_reconcile_job())
    asyncio.create_task(run_meta_data_deletion_reconcile_job())
    asyncio.create_task(run_customer_reply_reconcile_job())
    asyncio.create_task(run_web_chat_release_pending_reconcile_job())
    asyncio.create_task(run_tiktok_comment_sync_job())
    asyncio.create_task(run_meta_social_comment_sync_job())

    print("✅ Smart Messaging Scheduler started successfully")
    print("📅 Scheduled jobs:")
    print("   - Daily refresh: Daily at 00:01")
    print(f"   - Template dispatcher: Every {dispatcher_interval_minutes} minute(s)")
    print(f"   - Queue monitor/sender: Every {monitor_interval_minutes} minute(s)")
    print("   - Smart Follow-Up worker: Every 1 minute")
    print("   - Inbound event reconcile: Every 1 minute")
    print("   - Meta data deletion reconcile: Every 1 minute per node")
    print("   - Customer reply reconcile: Every 1 minute")
    print("   - Web Chat release pending reconcile: Every 1 minute")
    print("   - TikTok comment sync: Every 1 minute")
    print("   - Meta social comment sync: Every 1 minute")
    print("=" * 60)

    app_state.scheduler = scheduler
    return scheduler
