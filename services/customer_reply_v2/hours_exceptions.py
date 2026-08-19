"""Attach tenant closed-day exceptions when Luna selected hours or a branch.

Does not dump other branches. Off-day rules are typically few and tenant-wide.
"""

from __future__ import annotations

import json
from typing import Any

from services.cm.off_days import evaluate_off_days


def closed_days_snapshot(sections: dict[str, Any] | None) -> dict[str, Any]:
    payload = (sections or {}).get("off_days") or {}
    status = evaluate_off_days(payload if isinstance(payload, dict) else {})
    branch_payload = (sections or {}).get("branches") or {}
    specific = []
    if isinstance(branch_payload, dict):
        raw_rules = branch_payload.get("specific_off_rules") or []
        if isinstance(raw_rules, list):
            specific = [row for row in raw_rules if isinstance(row, dict)]
    return {
        "tenant_closed_days": {
            "timezone": status.get("timezone"),
            "weekly_off_days": status.get("weekly_off_days") or [],
            "specific_off_days": status.get("specific_off_days") or [],
            "notes": status.get("notes") or "",
        },
        "location_specific_off_rules": specific,
    }


def merge_closed_days_into_content(content: str, extra: dict[str, Any]) -> str:
    if not extra:
        return content
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        parsed.update(extra)
        return json.dumps(parsed, ensure_ascii=False)
    return f"{content}\n{json.dumps(extra, ensure_ascii=False)}".strip()
