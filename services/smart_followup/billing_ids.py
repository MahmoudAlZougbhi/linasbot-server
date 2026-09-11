"""Follow-up message-hold ids. Settle every candidate generate may have reserved."""

from __future__ import annotations

from typing import Any

from services.smart_followup.idempotency import canonical_sfu_key


def leftover_followup_pins(job: Any) -> tuple[str, ...]:
    """Conversation and minted Brain ids for a leftover follow-up hold."""
    conv = str(getattr(job, "conversation_id", "") or "").strip()
    goal = str(getattr(job, "goal", "") or "").strip()
    raw = str(getattr(job, "idempotency_key", "") or "").strip()
    minted = f"sfu:{conv}:{goal}" if conv and goal else ""
    canonical = ""
    if raw:
        try:
            canonical = canonical_sfu_key(raw)
        except ValueError:
            canonical = ""
    return tuple(item for item in (raw, canonical, minted, conv) if item)


def followup_operation_ids(snapshot: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    raw = str(snapshot.get("idempotency_key") or "").strip()
    conv = str(snapshot.get("conversation_id") or "").strip()
    goal = str(snapshot.get("goal") or "").strip()
    minted = f"sfu:{conv}:{goal}" if conv and goal else ""
    canonical = ""
    if raw:
        try:
            canonical = canonical_sfu_key(raw)
        except ValueError:
            canonical = ""
    primary = canonical or raw or minted
    extras = tuple(item for item in (raw, canonical, minted) if item)
    return primary, extras


def settle_followup_from_snapshot(tenant_id: str, snapshot: dict[str, Any], *, accepted: bool) -> None:
    from services.customer_ai.billing import settle_followup_send

    operation_id, extras = followup_operation_ids(snapshot)
    settle_followup_send(
        tenant_id=tenant_id,
        operation_id=operation_id,
        accepted=accepted,
        extra_ids=extras,
    )
