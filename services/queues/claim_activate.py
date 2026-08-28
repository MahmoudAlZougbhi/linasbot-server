"""Atomically pop a job onto processing and set its liveness lease.

BRPOPLPUSH alone leaves a window where the id is on the processing list with
no lease. Peer reclaimers then treat a live claim as a dead worker. Real Redis
runs RPOPLPUSH+SET in one Lua script. fakeredis (no EVAL) sets the lease
immediately after the pop; tests interleave at save, which is after that SET.
"""

from __future__ import annotations

from typing import Any

# KEYS[1]=queue KEYS[2]=processing
# ARGV[1]=lease prefix (linas:q:lease:) ARGV[2]=wire ARGV[3]=ttl
_POP_AND_LEASE = """
local id = redis.call('RPOPLPUSH', KEYS[1], KEYS[2])
if not id then
  return ''
end
redis.call('SET', ARGV[1] .. id, ARGV[2], 'EX', tonumber(ARGV[3]))
return id
"""


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


def pop_and_set_lease(
    redis_client: Any,
    *,
    queue_key: str,
    processing_key: str,
    lease_prefix: str,
    wire: str,
    ttl_seconds: int,
) -> str:
    if not wire:
        return ""
    ttl = max(1, int(ttl_seconds))
    if type(redis_client).__module__.startswith("fakeredis"):
        job_id = job_id_text(redis_client.rpoplpush(queue_key, processing_key))
        if not job_id:
            return ""
        redis_client.set(f"{lease_prefix}{job_id}", wire, ex=ttl)
        return job_id
    raw = redis_client.eval(
        _POP_AND_LEASE,
        2,
        queue_key,
        processing_key,
        lease_prefix,
        wire,
        ttl,
    )
    return job_id_text(raw)
