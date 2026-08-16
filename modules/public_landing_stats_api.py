"""Public landing aggregates — unauthenticated, rate-limited, no PII."""

from __future__ import annotations

from typing import Any

from modules.core import app
from services.public_landing_stats import collect_public_landing_stats


@app.get("/api/public/landing-stats")
async def public_landing_stats() -> Any:
    """Live marketing counters: subscribers and AI replies (messages + comments)."""
    return collect_public_landing_stats()
