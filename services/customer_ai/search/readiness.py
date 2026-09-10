"""Search store readiness. Missing pgvector/Voyage is typed, not silent lexical success."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.customer_ai.flags import voyage_configured


@dataclass(frozen=True)
class SearchReadiness:
    ready: bool
    pgvector: bool
    voyage: bool
    reason: str


def probe_pgvector(session: Any | None = None) -> bool:
    if session is None:
        return False
    try:
        row = session.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        ).scalar()
        return bool(row)
    except Exception:
        return False


def search_readiness(*, session: Any | None = None) -> SearchReadiness:
    has_vector = probe_pgvector(session)
    has_voyage = voyage_configured()
    if not has_voyage:
        return SearchReadiness(False, has_vector, False, "provider_not_configured")
    if not has_vector:
        return SearchReadiness(False, False, True, "index_not_ready")
    return SearchReadiness(True, True, True, "ok")
