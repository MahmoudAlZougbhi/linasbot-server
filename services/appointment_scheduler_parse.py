"""Appointment date parsing helper (LOC split)."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def parse_appointment_date(date_str: Any) -> Any:
    """
    Parse appointment date from backend format
    Backend returns: "27/10/2025 05:00:00 PM"  (DD/MM/YYYY HH:MM:SS AM/PM)
    """
    if not date_str:
        return None

    try:
        # Format from backend: "27/10/2025 05:00:00 PM"
        return datetime.strptime(date_str, "%d/%m/%Y %I:%M:%S %p")
    except ValueError:
        # Try other formats
        for fmt in ["%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None
