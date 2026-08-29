"""Armed soak jobs stop at the OpenAI request gate. Production never uses this."""

from __future__ import annotations

from typing import Any


def maybe_finish_soak_at_openai_gate(
    *,
    soak: bool,
    rec: Any,
    event_id: str,
) -> dict[str, Any] | None:
    """Mark the pipeline ready for OpenAI without calling the model or Graph."""

    if not soak:
        return None
    from services.scale.inbound_event_store import mark_inbound_state
    from services.scale.rate_window import bump

    mark_inbound_state(
        event_id,
        state="completed",
        outbound_status="openai_gate_reached",
        last_error="soak_pipeline_only",
    )
    bump("openai_ready")
    return {
        "ok": True,
        "kind": str(getattr(rec, "kind", "") or ""),
        "event_id": event_id,
        "openai_gate": True,
        "soak": True,
    }
