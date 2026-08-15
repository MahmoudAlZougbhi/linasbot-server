"""Unified Location & Opening Hours — normalize, legacy merge, runtime derivation."""

from __future__ import annotations

import copy
from typing import Any

from services.cm.schemas import (
    BranchesSection,
    BranchRecord,
    OffDaysSection,
    OpeningHoursDay,
    OpeningHoursSchedule,
    OpeningHoursSection,
)

WEEKDAY_KEYS: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def empty_branch_day() -> dict[str, Any]:
    return {"enabled": False, "open": "", "close": "", "off_day": False, "note": None}


def empty_weekly_schedule() -> dict[str, Any]:
    return {day: empty_branch_day() for day in WEEKDAY_KEYS}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_branch_day(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        "enabled": bool(row.get("enabled")),
        "open": str(row.get("open") or "").strip(),
        "close": str(row.get("close") or "").strip(),
        "off_day": bool(row.get("off_day")),
        "note": row.get("note"),
    }


def normalize_weekly_schedule(raw: Any) -> dict[str, Any]:
    src = _as_dict(raw)
    return {day: normalize_branch_day(src.get(day)) for day in WEEKDAY_KEYS}


def branch_has_schedule(branch: dict[str, Any]) -> bool:
    ws = normalize_weekly_schedule(branch.get("weekly_schedule"))
    for day in WEEKDAY_KEYS:
        if ws[day].get("enabled"):
            return True
    return False


def branches_section_has_unified_schedule(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    items = payload.get("items")
    if not isinstance(items, list):
        return False
    return any(isinstance(it, dict) and branch_has_schedule(it) for it in items)


def _opening_hours_day_to_branch_day(oh_day: dict[str, Any]) -> dict[str, Any]:
    closed = bool(oh_day.get("closed"))
    open_t = str(oh_day.get("open") or "").strip()
    close_t = str(oh_day.get("close") or "").strip()
    if closed:
        return {"enabled": True, "open": "", "close": "", "off_day": True, "note": None}
    if open_t and close_t:
        return {"enabled": True, "open": open_t, "close": close_t, "off_day": False, "note": None}
    return empty_branch_day()


def schedule_dict_to_weekly(schedule: dict[str, Any]) -> dict[str, Any]:
    weekly = empty_weekly_schedule()
    for day in WEEKDAY_KEYS:
        weekly[day] = _opening_hours_day_to_branch_day(_as_dict(schedule.get(day)))
    return weekly


def normalize_branch_record(raw: dict[str, Any]) -> dict[str, Any]:
    out = dict(raw)
    out["weekly_schedule"] = normalize_weekly_schedule(out.get("weekly_schedule"))
    return out


def normalize_branches_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    items = out.get("items")
    if isinstance(items, list):
        out["items"] = [normalize_branch_record(it) if isinstance(it, dict) else it for it in items]
    rules = out.get("specific_off_rules")
    if not isinstance(rules, list):
        out["specific_off_rules"] = []
    if not str(out.get("timezone") or "").strip():
        out["timezone"] = "Asia/Beirut"
    return out


def _label_text(labels: Any) -> str:
    if not isinstance(labels, dict):
        return ""
    return " ".join(str(labels.get(k) or "") for k in ("ar", "en", "fr", "franco")).strip()


def _find_branch_for_schedule(items: list[dict[str, Any]], schedule: dict[str, Any]) -> dict[str, Any] | None:
    sid = str(schedule.get("id") or "").strip()
    title = str(schedule.get("title") or "").strip()
    for branch in items:
        if sid and str(branch.get("id") or "") == sid:
            return branch
        if title and _label_text(branch.get("labels")) == title:
            return branch
    return None


def merge_opening_hours_into_branches(
    branches_payload: dict[str, Any],
    opening_hours_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(opening_hours_payload, dict):
        return branches_payload
    oh_items = opening_hours_payload.get("items")
    if not isinstance(oh_items, list) or not oh_items:
        return branches_payload
    out = copy.deepcopy(branches_payload)
    items: list[dict[str, Any]] = [
        normalize_branch_record(it) if isinstance(it, dict) else it for it in (out.get("items") or [])
    ]
    for schedule in oh_items:
        if not isinstance(schedule, dict):
            continue
        matched = _find_branch_for_schedule(items, schedule)
        if matched is not None:
            if not branch_has_schedule(matched):
                matched["weekly_schedule"] = schedule_dict_to_weekly(schedule)
            continue
        sid = str(schedule.get("id") or "").strip() or f"hours_{len(items) + 1}"
        title = str(schedule.get("title") or "").strip()
        items.append(
            normalize_branch_record(
                {
                    "id": sid,
                    "labels": {"en": title, "ar": "", "fr": "", "franco": ""},
                    "address": "",
                    "street": "",
                    "building": "",
                    "floor": "",
                    "country": "",
                    "maps_url": "",
                    "hours": {},
                    "weekly_schedule": schedule_dict_to_weekly(schedule),
                    "available": True,
                    "notes": schedule.get("notes"),
                }
            )
        )
    out["items"] = items
    return out


def merge_off_days_into_branches(
    branches_payload: dict[str, Any],
    off_days_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(off_days_payload, dict):
        return branches_payload
    out = copy.deepcopy(branches_payload)
    tz = str(off_days_payload.get("timezone") or "").strip()
    if tz:
        out["timezone"] = tz
    rules = off_days_payload.get("rules")
    if not isinstance(rules, list):
        return out
    items: list[dict[str, Any]] = [
        normalize_branch_record(it) if isinstance(it, dict) else it for it in (out.get("items") or [])
    ]
    specific: list[Any] = list(out.get("specific_off_rules") or [])
    seen_ids = {str(r.get("id")) for r in specific if isinstance(r, dict)}
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        kind = str(rule.get("kind") or "")
        if kind in {"date", "range"}:
            rid = str(rule.get("id") or "")
            if rid and rid not in seen_ids:
                specific.append(rule)
                seen_ids.add(rid)
        elif kind == "weekly" and rule.get("weekday") is not None:
            try:
                weekday = int(rule["weekday"])
            except (TypeError, ValueError):
                continue
            if weekday < 0 or weekday > 6:
                continue
            day_key = WEEKDAY_KEYS[weekday]
            for branch in items:
                ws = normalize_weekly_schedule(branch.get("weekly_schedule"))
                row = ws[day_key]
                if not row.get("enabled"):
                    row["enabled"] = True
                    row["off_day"] = True
                ws[day_key] = row
                branch["weekly_schedule"] = ws
    out["items"] = items
    out["specific_off_rules"] = specific
    return out


def enrich_branches_from_legacy_drafts(
    tenant_id: str,
    branches_payload: dict[str, Any],
) -> dict[str, Any]:
    from services.cm.atomic_io import read_json_object
    from services.cm.storage import draft_section_path

    out = normalize_branches_payload(branches_payload)
    if branches_section_has_unified_schedule(out):
        return out
    oh_path = draft_section_path(tenant_id, "opening_hours")
    off_path = draft_section_path(tenant_id, "off_days")
    oh_payload: dict[str, Any] | None = None
    off_payload: dict[str, Any] | None = None
    if oh_path.exists():
        envelope = read_json_object(oh_path)
        oh_payload = _as_dict(envelope.get("payload"))
    if off_path.exists():
        envelope = read_json_object(off_path)
        off_payload = _as_dict(envelope.get("payload"))
    out = merge_opening_hours_into_branches(out, oh_payload)
    out = merge_off_days_into_branches(out, off_payload)
    return normalize_branches_payload(out)


def _weekly_to_opening_hours_day(row: dict[str, Any]) -> OpeningHoursDay:
    if not row.get("enabled"):
        return OpeningHoursDay()
    if row.get("off_day"):
        return OpeningHoursDay(closed=True)
    open_t = str(row.get("open") or "").strip()
    close_t = str(row.get("close") or "").strip()
    if open_t and close_t:
        return OpeningHoursDay(open=open_t, close=close_t)
    return OpeningHoursDay()


def derive_opening_hours_section(
    branches: BranchesSection | dict[str, Any],
) -> OpeningHoursSection:
    section = branches if isinstance(branches, BranchesSection) else BranchesSection.model_validate(branches or {})
    schedules: list[OpeningHoursSchedule] = []
    for branch in section.items:
        if not branch_has_schedule(branch.model_dump(mode="json")):
            continue
        ws = branch.weekly_schedule
        schedules.append(
            OpeningHoursSchedule(
                id=branch.id,
                title=branch.schedule_title(),
                monday=_weekly_to_opening_hours_day(ws.monday.model_dump()),
                tuesday=_weekly_to_opening_hours_day(ws.tuesday.model_dump()),
                wednesday=_weekly_to_opening_hours_day(ws.wednesday.model_dump()),
                thursday=_weekly_to_opening_hours_day(ws.thursday.model_dump()),
                friday=_weekly_to_opening_hours_day(ws.friday.model_dump()),
                saturday=_weekly_to_opening_hours_day(ws.saturday.model_dump()),
                sunday=_weekly_to_opening_hours_day(ws.sunday.model_dump()),
                notes=branch.notes,
            )
        )
    return OpeningHoursSection(items=schedules, notes=section.notes)


def derive_off_days_section(branches: BranchesSection | dict[str, Any]) -> OffDaysSection:
    section = branches if isinstance(branches, BranchesSection) else BranchesSection.model_validate(branches or {})
    rules: list[dict[str, Any]] = []
    for rule in section.specific_off_rules:
        rules.append(rule.model_dump(mode="json"))
    return OffDaysSection(timezone=section.timezone, rules=rules, notes=section.notes)
