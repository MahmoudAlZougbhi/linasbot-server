"""Artifacts directory for offline eval JSON reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LATEST = Path(__file__).resolve().parent / "offline_suite_latest.json"


def latest_offline_artifact() -> dict[str, Any] | None:
    if not LATEST.exists():
        return None
    try:
        data = json.loads(LATEST.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return {
        "path": str(LATEST),
        "ok": bool(data.get("ok")),
        "case_count": (data.get("summary") or {}).get("case_count"),
        "suite": data.get("suite"),
    }
