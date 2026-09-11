"""Search store readiness. Missing pgvector/Voyage/pointer is typed, not silent success."""

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
    pointer_ready: bool = False


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


def search_readiness(*, session: Any | None = None, tenant_id: str = "") -> SearchReadiness:
    has_voyage = voyage_configured()
    if not has_voyage:
        return SearchReadiness(False, probe_pgvector(session), False, "provider_not_configured", False)

    tid = (tenant_id or "").strip()
    if session is None:
        # In-process memory store: extension is not live; pointer readiness is the gate.
        from services.customer_ai.search.store import tenant_pointer_ready

        pointer_ok = tenant_pointer_ready(None, tid) if tid else False
        if tid and not pointer_ok:
            return SearchReadiness(False, False, True, "index_not_ready", False)
        if tid and pointer_ok:
            return SearchReadiness(True, False, True, "ok", True)
        return SearchReadiness(False, False, True, "index_not_ready", False)

    has_vector = probe_pgvector(session)
    if not has_vector:
        return SearchReadiness(False, False, True, "index_not_ready", False)

    if tid:
        from services.customer_ai.search.store import tenant_pointer_ready

        pointer_ok = tenant_pointer_ready(session, tid)
        if not pointer_ok:
            return SearchReadiness(False, True, True, "index_not_ready", False)
        return SearchReadiness(True, True, True, "ok", True)
    return SearchReadiness(True, True, True, "ok", False)


def resolve_search_readiness(tenant_id: str) -> SearchReadiness:
    """Probe live WhatsApp/Postgres session when available; else memory pointers."""
    tid = (tenant_id or "").strip()
    try:
        from db.session import whatsapp_session

        with whatsapp_session(require=True) as session:
            return search_readiness(session=session, tenant_id=tid)
    except Exception:
        return search_readiness(session=None, tenant_id=tid)


def tenant_index_readiness(tenant_id: str) -> SearchReadiness:
    """Alias used by turn gates — tenant pointer + Voyage + pgvector when live."""
    return resolve_search_readiness(tenant_id)
