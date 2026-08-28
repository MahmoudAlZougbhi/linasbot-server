"""Set the liveness lease before the job hash is marked processing.

Popping onto the processing list without a lease let peer reclaimers treat a
live claim as a dead worker (lease_expired + duplicate AI). The lease key is
written immediately after the pop, before get/save. Reclaim ignores jobs that
are not yet status=processing so the one-command gap cannot steal work.
"""

from __future__ import annotations

from typing import Any


def job_id_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    text = str(value)
    return "" if text in {"", "None", "False"} else text


def set_claim_lease(
    redis_client: Any,
    *,
    job_id: str,
    lease_prefix: str,
    wire: str,
    ttl_seconds: int,
) -> None:
    jid = job_id_text(job_id)
    if not jid or not wire:
        return
    redis_client.set(f"{lease_prefix}{jid}", wire, ex=max(1, int(ttl_seconds)))
