"""Eval artifact helpers (no secrets)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
HOST_DIR = Path("/var/lib/linasbot/customer-ai-evals")
LATEST = ARTIFACT_DIR / "offline_suite_latest.json"


def durable_report_path(name: str) -> Path:
    """Production host dir when present; repo artifacts for local/CI."""
    if HOST_DIR.parent.is_dir():
        HOST_DIR.mkdir(parents=True, exist_ok=True)
        return HOST_DIR / name
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACT_DIR / name


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
