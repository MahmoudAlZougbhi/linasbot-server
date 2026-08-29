"""Armed soak jobs stop at the OpenAI request gate. Production never uses this."""

from __future__ import annotations

from typing import Any


def maybe_finish_soak_at_openai_gate(
    *,
    soak: bool,
    kind: str,
    event_id: str,
) -> dict[str, Any] | None:
    """Count OpenAI-gate readiness after Redis claim. No Firestore on this path."""

    if not soak:
        return None
    from services.scale.rate_window import bump

    bump("openai_ready")
    return {
        "ok": True,
        "kind": str(kind or ""),
        "event_id": event_id,
        "openai_gate": True,
        "soak": True,
    }
