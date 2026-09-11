"""Atomic index switch live proof for Customer Brain lab."""

from __future__ import annotations

import os
from typing import Any, Callable

from services.customer_ai.flags import voyage_configured
from services.customer_ai.providers.spaces import KNOWLEDGE_DOCUMENT
from services.customer_ai.providers.voyage_client import VoyageContractError
from services.customer_ai.retrieve.cards import load_published_cards
from services.customer_ai.search.contextual_index import build_and_activate_contextual_index
from services.customer_ai.search.store import activate_pointer, query_similar, rollback_pointer


async def atomic_switch_live(
    *,
    tenant_id: str,
    gate: Callable[..., dict[str, Any]],
    session_factory: Callable[[], Any],
) -> dict[str, Any]:
    """Prove candidate→activate→query→rollback without requiring fresh Voyage embeds."""
    if not (os.getenv("LINAS_WHATSAPP_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip():
        return gate("BLOCKED", "DATABASE_URL missing")
    from sqlalchemy import text

    try:
        with session_factory() as session:
            row = session.execute(
                text(
                    """
                    SELECT space_id, index_version, COUNT(*) AS n
                    FROM customer_ai_search_documents
                    WHERE tenant_id = :tenant_id
                      AND space_id = :space_id
                      AND source_family IN ('knowledge','care','faq')
                      AND embedding IS NOT NULL
                    GROUP BY space_id, index_version
                    ORDER BY n DESC
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "space_id": KNOWLEDGE_DOCUMENT.space_id},
            ).mappings().first()
            if not row or int(row["n"] or 0) < 1:
                if not voyage_configured():
                    return gate("BLOCKED", "VOYAGE_API_KEY")
                cards = load_published_cards(tenant_id)
                built = await build_and_activate_contextual_index(
                    cards, tenant_id=tenant_id, revision="switch_seed", session=session, activate=True
                )
                if not built.get("ready"):
                    detail = str(built.get("error") or built.get("reason") or "seed_failed")
                    if "429" in detail:
                        return gate("BLOCKED", "voyage_rate_limited")
                    return gate("FAIL", detail)
                v1 = str(built.get("version") or "")
                space_id = str(built.get("space_id") or KNOWLEDGE_DOCUMENT.space_id)
            else:
                v1 = str(row["index_version"])
                space_id = str(row["space_id"])
                activate_pointer(
                    session,
                    tenant_id=tenant_id,
                    space_id=space_id,
                    source_family="knowledge_ctx",
                    version=v1,
                    count=int(row["n"] or 0),
                    source_revision="lab",
                )
            v2 = f"{v1}:sw"
            try:
                session.execute(
                    text(
                        """
                        INSERT INTO customer_ai_search_documents
                            (id, tenant_id, space_id, source_family, source_id, chunk_id, parent_id,
                             index_version, source_revision, content_hash, title, search_text, visible, embedding)
                        SELECT
                            LEFT(md5(id || CAST(:suffix AS text)), 128), tenant_id, space_id, source_family, source_id,
                            chunk_id, parent_id, :v2, source_revision, content_hash, title, search_text, visible, embedding
                        FROM customer_ai_search_documents
                        WHERE tenant_id = :tenant_id AND space_id = :space_id AND index_version = :v1
                        ON CONFLICT (tenant_id, space_id, source_id, chunk_id, index_version) DO NOTHING
                        """
                    ),
                    {"tenant_id": tenant_id, "space_id": space_id, "v1": v1, "v2": v2, "suffix": ":sw"},
                )
            except Exception:
                session.rollback()
                raise
            n2 = session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM customer_ai_search_documents
                    WHERE tenant_id = :tenant_id AND space_id = :space_id AND index_version = :v2
                    """
                ),
                {"tenant_id": tenant_id, "space_id": space_id, "v2": v2},
            ).scalar()
            mid = query_similar(
                session,
                tenant_id=tenant_id,
                space_id=space_id,
                vector=[0.01] * 1024,
                families={"knowledge", "care", "faq"},
                limit=5,
                index_version=v1,
            )
            activate_pointer(
                session,
                tenant_id=tenant_id,
                space_id=space_id,
                source_family="knowledge_ctx",
                version=v2,
                count=int(n2 or 0),
                source_revision="lab_cand",
            )
            after = query_similar(
                session,
                tenant_id=tenant_id,
                space_id=space_id,
                vector=[0.01] * 1024,
                families={"knowledge", "care", "faq"},
                limit=5,
            )
            after_versions = {
                str(
                    session.execute(
                        text("SELECT index_version FROM customer_ai_search_documents WHERE id = :id"),
                        {"id": item.doc_id},
                    ).scalar()
                    or ""
                )
                for item in after.items
            }
            rolled = rollback_pointer(
                session,
                tenant_id=tenant_id,
                space_id=space_id,
                source_family="knowledge_ctx",
            )
            back = query_similar(
                session,
                tenant_id=tenant_id,
                space_id=space_id,
                vector=[0.01] * 1024,
                families={"knowledge", "care", "faq"},
                limit=5,
            )
    except VoyageContractError as exc:
        if "429" in str(exc):
            return gate("BLOCKED", "voyage_rate_limited")
        return gate("FAIL", str(exc)[:160])
    except Exception as exc:
        return gate("FAIL", f"{type(exc).__name__}:{str(exc)[:160]}")
    ok = (
        v1 != v2
        and int(n2 or 0) >= 1
        and mid.outcome in {"found", "not_found"}
        and after.outcome in {"found", "not_found"}
        and bool(rolled.get("ok"))
        and (not after_versions or after_versions == {v2})
        and str((rolled.get("pointer") or {}).get("active_version") or "") == v1
    )
    return gate(
        "PASS" if ok else "FAIL",
        "sql_candidate_copy→activate→query→rollback",
        v1=v1,
        v2=v2,
        mid_hits=len(mid.items),
        after_hits=len(after.items),
        back_hits=len(back.items),
        rollback=rolled,
        after_versions=sorted(after_versions),
        n2=int(n2 or 0),
    )
