"""Artifacts directory for offline eval JSON reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LATEST = Path(__file__).resolve().parent / "offline_suite_latest.json"
HOST_DIR = Path("/var/lib/linasbot/customer-ai-evals")


def durable_report_path(name: str) -> Path:
    """Production host dir when present; repo artifacts for local/CI."""
    if HOST_DIR.parent.is_dir():
        HOST_DIR.mkdir(parents=True, exist_ok=True)
        return HOST_DIR / name
    LATEST.parent.mkdir(parents=True, exist_ok=True)
    return LATEST.parent / name


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
