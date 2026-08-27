"""Place worker replicas across nodes. Dead nodes are skipped up to remaining cap."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeCapacity:
    node_id: str
    healthy: bool
    cpu_pct: float
    mem_pct: float
    worker_cap: int
    current_workers: int = 0


def place_workers(desired: int, nodes: list[NodeCapacity]) -> dict[str, int]:
    """Spread desired workers across healthy nodes, busiest-capacity first.

    If a node is dead, remaining healthy nodes absorb up to their cap.
    Never assigns more than worker_cap per node.
    """
    wanted = max(0, int(desired))
    healthy = [item for item in nodes if item.healthy and item.worker_cap > 0]
    assignment = {item.node_id: 0 for item in nodes}
    if not healthy or wanted == 0:
        return assignment

    def score(node: NodeCapacity) -> tuple[float, float, int]:
        return (node.cpu_pct + node.mem_pct, node.cpu_pct, -node.worker_cap)

    remaining = wanted
    while remaining > 0:
        progressed = False
        for node in sorted(healthy, key=score):
            if assignment[node.node_id] >= node.worker_cap:
                continue
            assignment[node.node_id] += 1
            remaining -= 1
            progressed = True
            if remaining == 0:
                break
        if not progressed:
            break
    return assignment


def at_safe_cap(nodes: list[NodeCapacity], *, assignments: dict[str, int] | None = None) -> bool:
    placed = assignments or {item.node_id: item.current_workers for item in nodes}
    healthy = [item for item in nodes if item.healthy]
    if not healthy:
        return True
    return all(int(placed.get(item.node_id) or 0) >= item.worker_cap for item in healthy)
