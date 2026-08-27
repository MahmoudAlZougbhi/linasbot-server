"""Map cluster desired replicas to in-process claim slots on this node."""

from __future__ import annotations

import os

from services.omnichannel.worker_pool import concurrency_for


def slot_count_for(queue: str) -> int:
    """In-node scale first: extra claim loops in the existing systemd worker.

    Droplet count stays at the HA pair unless the node scaler later proves
    sustained pressure past this cap.
    """
    base = concurrency_for(queue)
    cap = _cap(queue, base)
    if queue not in {"high_priority", "background"}:
        return min(cap, base)
    try:
        from services.scale.replica_controller import apply_enabled, current_replicas

        if not apply_enabled():
            return min(cap, base)
        desired = max(1, int(current_replicas().workers))
        nodes = max(1, int(os.getenv("LINAS_CLUSTER_NODES") or "2"))
        share = max(1, (desired + nodes - 1) // nodes)
        return min(cap, share)
    except Exception:
        return min(cap, base)


def _cap(queue: str, base: int) -> int:
    env_name = {
        "high_priority": "LINAS_QUEUE_CONCURRENCY_CAP_HIGH",
        "background": "LINAS_QUEUE_CONCURRENCY_CAP_BACKGROUND",
        "interactive": "LINAS_QUEUE_CONCURRENCY_CAP_INTERACTIVE",
        "expensive": "LINAS_QUEUE_CONCURRENCY_CAP_EXPENSIVE",
    }.get(queue)
    raw = (os.getenv(env_name) or "").strip() if env_name else ""
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            return base
    # 2 vCPU / 2 GiB HA nodes: do not let one queue exceed these slots.
    defaults = {"high_priority": 8, "background": 4, "interactive": 4, "expensive": 1}
    return int(defaults.get(queue, base))
