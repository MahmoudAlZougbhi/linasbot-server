"""Phone/datetime/appointment helpers for DailyTemplateDispatcher."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _normalize_phone(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("+", "").replace(" ", "").replace("-", "")


def _parse_api_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    formats = (
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _extract_appointments(result: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(result, dict) or not result.get("success"):
        return []
    data = result.get("data", {})
    if isinstance(data, dict):
        appointments = data.get("appointments", [])
    elif isinstance(data, list):
        appointments = data
    else:
        appointments = []
    return appointments if isinstance(appointments, list) else []
