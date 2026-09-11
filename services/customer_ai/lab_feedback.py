"""Owner Lab human review marks for Brain turns (diagnostic only — no auto-train)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

ReviewLabel = Literal[
    "correct",
    "partially_correct",
    "wrong",
    "missing_info",
    "bad_retrieval",
    "bad_grounding",
    "wrong_language",
    "bad_handoff",
]

_STORE: list[dict[str, Any]] = []


@dataclass(frozen=True)
class LabReview:
    tenant_id: str
    turn_id: str
    label: ReviewLabel
    note: str = ""


def record_lab_review(review: LabReview) -> dict[str, Any]:
    row = {
        "tenant_id": review.tenant_id,
        "turn_id": review.turn_id,
        "label": review.label,
        "note": (review.note or "")[:500],
        "at": datetime.now(timezone.utc).isoformat(),
        "auto_train": False,
    }
    _STORE.append(row)
    return row


def list_lab_reviews(*, tenant_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
    rows = list(_STORE)
    if tenant_id.strip():
        rows = [r for r in rows if r.get("tenant_id") == tenant_id.strip()]
    return rows[-max(1, limit) :]


def reset_lab_reviews_for_tests() -> None:
    _STORE.clear()
