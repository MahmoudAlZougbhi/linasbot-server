"""Capped Firestore reads for the inbound reconcile watchdog.

An active-state query bills one read for every matching document. The watchdog
only acts on a batch, so the query uses that same cap.
"""

from __future__ import annotations

import os
from typing import Any

from services.scale.inbound_event_store_models import ACTIVE_STATES, InboundEventRecord

# The Redis lock is held for most of this interval so the peer node skips the scan.
RECONCILE_INTERVAL_MINUTES = 10
RECONCILE_LOCK_TTL_SECONDS = 540


def active_scan_limit() -> int:
    """How many active documents one watchdog pass may read and act on."""
    raw = (os.getenv("LINAS_INBOUND_RECONCILE_BATCH") or "32").strip()
    try:
        return max(1, min(200, int(raw)))
    except ValueError:
        return 32


def _record_from_snapshot(snapshot: Any) -> InboundEventRecord | None:
    if getattr(snapshot, "exists", True) is False:
        return None
    raw = snapshot.to_dict()
    if not isinstance(raw, dict):
        raise ValueError("Inbound event snapshot is not a mapping")
    return InboundEventRecord.from_dict(raw)


def shared_active_records(
    collection: Any,
    *,
    local_event_ids: set[str],
    query_limit: int | None = None,
) -> dict[str, InboundEventRecord]:
    """Read a capped active query, plus primary state for local candidates."""

    from google.cloud.firestore_v1.base_query import FieldFilter

    query = collection.where(filter=FieldFilter("state", "in", sorted(ACTIVE_STATES)))
    if query_limit is not None:
        query = query.limit(max(1, int(query_limit)))
    primary: dict[str, InboundEventRecord] = {}
    scanned = 0
    for snapshot in query.stream(timeout=8, retry=None):
        scanned += 1
        record = _record_from_snapshot(snapshot)
        if record is not None:
            primary[record.event_id] = record
    from services.scale.firestore_usage import record_usage

    record_usage("inbound_active_scan", reads=max(1, scanned))

    # An active local cache can be stale after a peer completed the shared
    # record. Read its primary document even though terminal records are absent
    # from the active query, otherwise this node could requeue completed work.
    for event_id in local_event_ids - primary.keys():
        record = _record_from_snapshot(collection.document(event_id).get())
        if record is not None:
            primary[record.event_id] = record
    return primary
