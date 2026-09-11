"""Human-readable Brain stage timeline for Owner message inspector."""

from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def stamp(
    extra: dict[str, Any] | None, stage: str, *, title: str, detail: dict[str, Any] | None = None
) -> dict[str, Any]:
    out = dict(extra or {})
    timeline = list(out.get("stage_timeline") or [])
    row: dict[str, Any] = {
        "stage": stage,
        "title": title,
        "at": _now_iso(),
    }
    if detail:
        row["detail"] = {key: value for key, value in detail.items() if value not in (None, "", [], {})}
    timeline.append(row)
    out["stage_timeline"] = timeline
    return out


class StageTimer:
    def __init__(self) -> None:
        self._started = monotonic()

    def ms(self) -> int:
        return max(0, int((monotonic() - self._started) * 1000))


def evidence_preview(bundle: Any, *, limit: int = 8) -> list[dict[str, str]]:
    items = getattr(bundle, "items", None) or []
    rows: list[dict[str, str]] = []
    for item in items[:limit]:
        text = str(getattr(item, "text", "") or "")
        rows.append(
            {
                "id": str(getattr(item, "evidence_id", "") or ""),
                "family": str(getattr(item, "source_family", "") or ""),
                "title": str(getattr(item, "title", "") or ""),
                "preview": (text[:280] + ("…" if len(text) > 280 else "")).strip(),
            }
        )
    return rows


def public_flow_from_extra(extra: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Owner-facing stages only — no prompts, no code, no raw dumps."""
    rows: list[dict[str, Any]] = []
    for item in list((extra or {}).get("stage_timeline") or []):
        if not isinstance(item, dict):
            continue
        detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
        clean_detail = {
            key: detail[key]
            for key in (
                "ms",
                "channel",
                "history_count",
                "gate",
                "plan_tasks",
                "retrieval_outcome",
                "evidence",
                "faq_id",
                "decision",
                "message_units",
                "response_class",
                "billing_policy",
                "send_state",
                "provider_message_id",
                "cost_pending_events",
                "known_usd",
                "carry",
                "used_turns",
                "reason",
                "verification",
                "contradiction_detected",
                "index_version",
                "content_version",
            )
            if key in detail
        }
        rows.append(
            {
                "stage": str(item.get("stage") or ""),
                "title": str(item.get("title") or item.get("stage") or ""),
                "at": str(item.get("at") or ""),
                "detail": clean_detail,
            }
        )
    return rows
