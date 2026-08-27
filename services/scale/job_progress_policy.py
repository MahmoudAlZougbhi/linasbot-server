"""Stage-specific stuck thresholds. Not a global job max duration."""

from __future__ import annotations

import os
from typing import Final

# Defaults track typical OpenAI HTTP timeout (600s) when the client has no explicit cap.
_STAGE_DEFAULTS: Final[dict[str, int]] = {
    "received": 60,
    "persisted": 60,
    "queued": 60,
    "processing": 120,
    "luna_started": 600,
    "luna_completed": 120,
    "tera_started": 600,
    "tera_completed": 90,
    "ai_generated": 90,
    "delivery_started": 90,
    "delivery_unknown": 120,
    "delivery_confirmed": 60,
    "completed": 10**9,
}

_ENV_BY_STAGE: Final[dict[str, str]] = {
    "processing": "LINAS_PROGRESS_PROCESSING_STUCK_SEC",
    "luna_started": "LINAS_PROGRESS_LUNA_STUCK_SEC",
    "tera_started": "LINAS_PROGRESS_TERA_STUCK_SEC",
    "ai_generated": "LINAS_PROGRESS_AI_GENERATED_STUCK_SEC",
    "delivery_started": "LINAS_PROGRESS_DELIVERY_STUCK_SEC",
    "delivery_unknown": "LINAS_PROGRESS_DELIVERY_UNKNOWN_STUCK_SEC",
}


def grace_seconds() -> float:
    raw = (os.getenv("LINAS_PROGRESS_GRACE_SEC") or "15").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 15.0


def max_stuck_count() -> int:
    raw = (os.getenv("LINAS_PROGRESS_MAX_STUCK") or "3").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def stage_timeout_seconds(stage: str) -> float:
    name = (stage or "processing").strip() or "processing"
    env_key = _ENV_BY_STAGE.get(name)
    if env_key:
        raw = (os.getenv(env_key) or "").strip()
        if raw:
            try:
                return max(5.0, float(raw))
            except ValueError:
                pass
    return float(_STAGE_DEFAULTS.get(name, 180))
