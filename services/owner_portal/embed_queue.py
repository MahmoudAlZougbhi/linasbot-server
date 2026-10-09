"""Failed owner embeds wait here for a later retry. The queue is in-process."""

from __future__ import annotations

_PENDING: list[dict[str, object]] = []


def reset_embed_queue_for_tests() -> None:
    _PENDING.clear()


def enqueue_failed(feature: str, texts: list[str]) -> None:
    _PENDING.append({"feature": feature, "texts": [item for item in texts if (item or "").strip()], "state": "pending"})


def pending() -> list[dict[str, object]]:
    return list(_PENDING)


def mark_ready(feature: str) -> int:
    changed = 0
    for item in _PENDING:
        if item.get("feature") == feature and item.get("state") == "pending":
            item["state"] = "ready"
            changed += 1
    return changed
