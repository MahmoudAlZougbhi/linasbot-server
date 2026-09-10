"""Customer Brain enablement. Default off — not a live-customer switch."""

from __future__ import annotations

import os
from typing import Any


def customer_brain_enabled() -> bool:
    raw = (os.getenv("CUSTOMER_BRAIN_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def voyage_api_key() -> str:
    if "VOYAGE_API_KEY" in os.environ:
        return (os.environ.get("VOYAGE_API_KEY") or "").strip()
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        return ""
    return (os.getenv("VOYAGE_API_KEY") or "").strip()


def voyage_configured() -> bool:
    return bool(voyage_api_key())


def flags_snapshot() -> dict[str, Any]:
    return {
        "customer_brain_enabled": customer_brain_enabled(),
        "voyage_configured": voyage_configured(),
        "customer_engine": "brain" if customer_brain_enabled() else "removed",
    }
