"""Per-node reconciliation for shared Meta data-deletion requests."""

from __future__ import annotations


async def run_meta_data_deletion_reconcile_job() -> None:
    """Sanitize this node's private ledger and publish a generation-bound ack.

    This job intentionally has no cluster-wide singleton lock: every configured
    node must run it and acknowledge its own local ledger before completion.
    """

    try:
        from services.meta_data_deletion import process_pending_meta_deletion_requests

        result = process_pending_meta_deletion_requests()
        examined = int(result.get("examined") or 0)
        if examined:
            print(
                "[meta-deletion-reconcile] "
                f"examined={examined} acknowledged={int(result.get('acknowledged') or 0)} "
                f"completed={int(result.get('completed') or 0)} pending={int(result.get('pending') or 0)} "
                f"errors={int(result.get('errors') or 0)}"
            )
    except Exception as exc:
        print(f"[meta-deletion-reconcile] failed type={type(exc).__name__}")
