"""Map cluster desired replicas to in-process claim slots on this node."""

from __future__ import annotations

import os

from services.omnichannel.worker_pool import concurrency_for


def cluster_node_count() -> int:
    """HA API pair by default. Extra worker nodes must not join the HTTP LB."""
    try:
        return max(1, int(os.getenv("LINAS_CLUSTER_NODES") or "2"))
    except ValueError:
        return 2


def per_node_high_cap() -> int:
    return _cap("high_priority", 16)


def cluster_in_node_worker_cap() -> int:
    """Software slot ceiling across this cluster. Not a DigitalOcean droplet cap.

    Raise ``LINAS_IN_NODE_WORKER_CAP`` or ``LINAS_QUEUE_CONCURRENCY_CAP_HIGH``
    to add in-process workers. Do not add API droplets to the load balancer.
    """
    raw = (os.getenv("LINAS_IN_NODE_WORKER_CAP") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return per_node_high_cap() * cluster_node_count()


def slot_count_for(queue: str) -> int:
    """In-node scale first: extra claim loops in the existing systemd worker.

    Droplet count stays at the HA pair unless the node scaler later proves
    sustained pressure past this cap. Production node-layer create is fail-closed.
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
        nodes = cluster_node_count()
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
    # In-process slots on the existing HA nodes. Not LB membership.
    defaults = {"high_priority": 16, "background": 8, "interactive": 4, "expensive": 1}
    return int(defaults.get(queue, base))
