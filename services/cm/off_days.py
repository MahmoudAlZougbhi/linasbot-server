"""Off-day / availability facts from published CM ``off_days`` section."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.cm.schemas import AnswerFact, OffDaysSection


def _parse_ymd(value: str) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def evaluate_off_days(
    section: OffDaysSection | dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return closed status and human-readable summary for the current local date."""
    policy = section if isinstance(section, OffDaysSection) else OffDaysSection.model_validate(section or {})
    try:
        tz = ZoneInfo(policy.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local_now = now.astimezone(tz) if now else datetime.now(tz)
    today = local_now.date()
    weekday = today.weekday()  # Mon=0

    closed_reasons: list[str] = []
    weekly_labels: list[str] = []
    specific_labels: list[str] = []
    weekday_names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

    for rule in policy.rules:
        reason = (rule.reason or "").strip() or "closed"
        if rule.kind == "weekly" and rule.weekday is not None:
            label = weekday_names[int(rule.weekday)] if 0 <= int(rule.weekday) <= 6 else f"weekday:{rule.weekday}"
            weekly_labels.append(f"{label} ({reason})")
            if int(rule.weekday) == weekday:
                closed_reasons.append(f"weekly:{label}:{reason}")
        elif rule.kind == "date":
            d = _parse_ymd(rule.date)
            if d is None:
                continue
            specific_labels.append(f"{d.isoformat()} ({reason})")
            if d == today:
                closed_reasons.append(f"date:{d.isoformat()}:{reason}")
        elif rule.kind == "range":
            start = _parse_ymd(rule.start_date)
            end = _parse_ymd(rule.end_date)
            if start is None or end is None:
                continue
            specific_labels.append(f"{start.isoformat()}–{end.isoformat()} ({reason})")
            if start <= today <= end:
                closed_reasons.append(f"range:{start.isoformat()}:{end.isoformat()}:{reason}")

    return {
        "timezone": str(tz),
        "local_date": today.isoformat(),
        "is_closed_today": bool(closed_reasons),
        "closed_reasons": closed_reasons,
        "weekly_off_days": weekly_labels,
        "specific_off_days": specific_labels,
        "notes": (policy.notes or "").strip(),
    }


def resolve_off_day_facts(
    section: OffDaysSection | dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[AnswerFact]:
    """Grounded availability facts for the answer packet (never invents hours)."""
    status = evaluate_off_days(section, now=now)
    facts: list[AnswerFact] = [
        AnswerFact(kind="off_days_timezone", value=status["timezone"], source_id="off_days:timezone"),
        AnswerFact(
            kind="business_closed_today",
            value="true" if status["is_closed_today"] else "false",
            source_id="off_days:today",
        ),
    ]
    if status["weekly_off_days"]:
        facts.append(
            AnswerFact(
                kind="weekly_off_days",
                value="; ".join(status["weekly_off_days"]),
                source_id="off_days:weekly",
            )
        )
    if status["specific_off_days"]:
        facts.append(
            AnswerFact(
                kind="specific_off_days",
                value="; ".join(status["specific_off_days"]),
                source_id="off_days:specific",
            )
        )
    if status["closed_reasons"]:
        facts.append(
            AnswerFact(
                kind="closed_today_reason",
                value="; ".join(status["closed_reasons"]),
                source_id="off_days:today_reason",
            )
        )
    if status["notes"]:
        facts.append(AnswerFact(kind="off_days_notes", value=status["notes"], source_id="off_days:notes"))
    return facts
