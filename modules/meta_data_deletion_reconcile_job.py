"""Per-node reconciliation for shared Meta data-deletion requests."""

from __future__ import annotations

import asyncio
from typing import Any


def _log_result(result: dict[str, Any]) -> None:
    examined = int(result.get("examined") or 0)
    if not examined:
        return
    print(
        "[meta-deletion-reconcile] "
        f"examined={examined} acknowledged={int(result.get('acknowledged') or 0)} "
        f"completed={int(result.get('completed') or 0)} pending={int(result.get('pending') or 0)} "
        f"errors={int(result.get('errors') or 0)}"
    )


async def run_meta_data_deletion_reconcile_job() -> None:
    """One node scans. Both nodes acknowledge the stored confirmation codes."""

    from services.integrations.meta.meta_deletion_scan import load_pending_codes, store_pending_codes
    from services.scale.firestore_quota_backoff import is_quota_error, note_quota_result, quota_backoff_active
    from services.scale.job_interval_lock import job_interval_lock

    if quota_backoff_active():
        return
    try:
        from services.integrations.meta.meta_data_deletion import process_pending_meta_deletion_requests

        with job_interval_lock("meta_deletion_pending_scan", ttl_seconds=50) as acquired:
            if acquired:
                try:
                    result = await asyncio.to_thread(process_pending_meta_deletion_requests, query_limit=32)
                    raw_codes = result.get("codes") if isinstance(result, dict) else []
                    store_pending_codes([str(code) for code in raw_codes] if isinstance(raw_codes, list) else [])
                    note_quota_result(None)
                    _log_result(result if isinstance(result, dict) else {})
                except Exception as exc:
                    note_quota_result(exc)
                    if is_quota_error(exc):
                        return
                    raise
                return
        codes = load_pending_codes()
        if codes is None:
            await asyncio.sleep(0.4)
            codes = load_pending_codes()
        if not codes:
            return
        result = await asyncio.to_thread(
            process_pending_meta_deletion_requests,
            confirmation_codes=codes,
        )
        note_quota_result(None)
        _log_result(result if isinstance(result, dict) else {})
    except Exception as exc:
        note_quota_result(exc)
        print(f"[meta-deletion-reconcile] failed type={type(exc).__name__}")
