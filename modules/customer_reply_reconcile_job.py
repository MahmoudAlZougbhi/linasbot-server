"""Periodic reconcile for stuck customer AI replies (A/B/C/D safe recovery)."""

from __future__ import annotations

from services.durable_event_claim import release_job_lock, try_acquire_job_lock


async def run_customer_reply_reconcile_job() -> None:
    if not try_acquire_job_lock("customer_reply_reconcile", ttl_seconds=55):
        return
    try:
        from services.customer_reply_reconcile_worker import reconcile_customer_replies

        result = await reconcile_customer_replies(dry_run=False, older_than_seconds=60.0)
        summary = result.get("summary") or {}
        metrics = result.get("metrics") or {}
        stuck = int(summary.get("stuck_events_count") or 0)
        if stuck or int(metrics.get("retry_success_count") or 0):
            print(
                f"[customer-reply-reconcile] stuck={stuck} "
                f"stale_claims={metrics.get('stale_claims_count', 0)} "
                f"retry_success={metrics.get('retry_success_count', 0)} "
                f"charged_undelivered={metrics.get('charged_without_delivery_count', 0)}"
            )
    except Exception as exc:
        print(f"[customer-reply-reconcile] failed type={type(exc).__name__}")
    finally:
        release_job_lock("customer_reply_reconcile")
