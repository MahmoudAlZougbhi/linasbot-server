"""Owner copilot Q&A. A close match answers with no model call."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from services.brain.providers.spaces import ENTITY_DOCUMENT
from services.owner_portal import owner_embed
from services.owner_portal.owner_embed import embed_one
from services.owner_portal.owner_kb_store import OWNER_KB_TENANT, _session

logger = logging.getLogger(__name__)

_FAMILY = "owner_qa"
# A measured near-copy ("…please?") scored 0.73 on the Voyage entity model.
# Questions that share the same product code can match a little lower.
# A different product code is rejected even when the sentence shape is the same.
_THRESHOLD = 0.72
_ENTITY_THRESHOLD = 0.55
_LABEL = re.compile(r"^(?:QA-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\s+)+", re.IGNORECASE)
_POLITE = re.compile(r"(?:\s+please|\s+لو سمحت)[.?!؟]*$", re.IGNORECASE)
_ENTITY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+", re.IGNORECASE)
_MARGIN = 0.05
_LANGS = ("ar", "en", "fr", "franco")
_LOCK = 2026100803


def _norm(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def list_qa() -> list[dict[str, Any]]:
    try:
        with _session() as session:
            if session is None:
                return []
            groups = session.execute(text("SELECT id, source_language, created_at FROM owner_copilot_qa")).all()
            variants = session.execute(
                text("SELECT qa_id, language, question, answer FROM owner_copilot_qa_variants")
            ).all()
    except Exception:
        return []
    by_id: dict[str, dict[str, Any]] = {
        str(row[0]): {
            "id": str(row[0]),
            "source_language": str(row[1] or "en"),
            "created_at": str(row[2] or ""),
            "variants": [],
        }
        for row in groups
    }
    for qa_id, language, question, answer in variants:
        bucket = by_id.get(str(qa_id))
        if bucket is None:
            continue
        bucket["variants"].append(
            {"language": str(language), "question": str(question or ""), "answer": str(answer or "")}
        )
    return list(by_id.values())


def save_qa(*, variants: list[dict[str, str]], source_language: str = "en", qa_id: str | None = None) -> str:
    item_id = (qa_id or "").strip() or uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    rows = [row for row in variants if row.get("question") and row.get("answer") and row.get("language") in _LANGS]
    with _session() as session:
        if session is None:
            raise RuntimeError("database_unavailable")
        session.execute(
            text(
                """
                INSERT INTO owner_copilot_qa (id, source_language, created_at)
                VALUES (:id, :lang, :created)
                ON CONFLICT (id) DO UPDATE SET source_language = excluded.source_language
                """
            ),
            {"id": item_id, "lang": source_language, "created": now},
        )
        for row in rows:
            session.execute(
                text(
                    """
                    INSERT INTO owner_copilot_qa_variants (qa_id, language, question, answer)
                    VALUES (:qa, :language, :question, :answer)
                    ON CONFLICT (qa_id, language) DO UPDATE
                    SET question = excluded.question, answer = excluded.answer
                    """
                ),
                {
                    "qa": item_id,
                    "language": row["language"],
                    "question": row["question"].strip(),
                    "answer": row["answer"].strip(),
                },
            )
        session.commit()
    _index(item_id, rows)
    return item_id


def search_forms(question: str) -> list[str]:
    """Full question plus the same question without a leading QA- label."""
    full = (question or "").strip()
    forms = [full] if full else []
    stripped = _LABEL.sub("", full).strip()
    if stripped and stripped.lower() != full.lower():
        forms.append(stripped)
    return forms


def query_forms(question: str) -> list[str]:
    """Search forms plus the same text without a trailing please."""
    forms = search_forms(question)
    seen = {form.lower() for form in forms}
    for form in list(forms):
        trimmed = _POLITE.sub("", form).strip()
        if trimmed and trimmed.lower() not in seen:
            seen.add(trimmed.lower())
            forms.append(trimmed)
    return forms


def _embed_forms(texts: list[str]) -> list[list[float] | None]:
    """Batch on the real client. A test that replaces embed_one still wins."""
    if embed_one is owner_embed.embed_one:
        return owner_embed.embed_batch(texts, query=False, feature="owner_qa")
    return [embed_one(text, query=False) for text in texts]


def _existing_texts() -> dict[str, str]:
    found: dict[str, str] = {}
    from services.brain.search.store import _MEMORY

    for bucket in _MEMORY.values():
        for row in bucket:
            if str(row.get("source_family") or "") == _FAMILY:
                found[str(row.get("id") or "")] = str(row.get("search_text") or "")
    try:
        with _session() as session:
            if session is None:
                return found
            rows = session.execute(
                text("SELECT id, search_text FROM customer_ai_search_documents WHERE source_family = :family"),
                {"family": _FAMILY},
            ).all()
    except Exception:
        return found
    for row in rows:
        found[str(row[0])] = str(row[1] or "")
    return found


def _index(qa_id: str, rows: list[dict[str, str]], *, enqueue: bool = True) -> bool:
    from services.brain.search.store import write_documents

    existing = _existing_texts()
    pending: list[tuple[dict[str, str], str, str, str]] = []
    for row in rows:
        for form in search_forms(row["question"]):
            suffix = row["language"] if form == row["question"].strip() else f"{row['language']}-core"
            doc_id = f"owner-qa-{qa_id}-{suffix}"
            if existing.get(doc_id) == form:
                continue
            pending.append((row, form, suffix, doc_id))
    if not pending:
        return True
    vectors = _embed_forms([item[1] for item in pending])
    docs: list[dict[str, Any]] = []
    kept: list[list[float]] = []
    missing = False
    for (row, form, suffix, doc_id), vector in zip(pending, vectors, strict=True):
        if not vector:
            missing = True
            logger.warning("owner qa variant %s/%s was not embedded", qa_id, row["language"])
            continue
        docs.append(
            {
                "id": doc_id,
                "tenant_id": OWNER_KB_TENANT,
                "space_id": ENTITY_DOCUMENT.space_id,
                "source_family": _FAMILY,
                "source_id": f"{qa_id}:{row['language']}",
                "chunk_id": suffix,
                "parent_id": qa_id,
                "index_version": "",
                "source_revision": "1",
                "content_hash": qa_id + suffix,
                "title": row["answer"][:200],
                "search_text": form,
                "visible": True,
            }
        )
        kept.append(vector)
    if not docs:
        logger.warning("owner qa %s stored no vectors", qa_id)
    else:
        with _session() as session:
            written = write_documents(session, docs, kept)
            if not written.get("ok"):
                logger.warning("owner qa %s vector write failed: %s", qa_id, written.get("reason"))
                missing = True
            elif session is not None:
                session.commit()
    if missing and enqueue:
        from services.owner_portal.embed_jobs import enqueue_embed

        enqueue_embed(kind="qa", ref_id=qa_id, payload={"rows": rows})
    return not missing


def _answer_for(qa_id: str, language: str) -> str:
    wanted = language if language in _LANGS else "en"
    fallback = ""
    for group in list_qa():
        if group["id"] != qa_id:
            continue
        for variant in group["variants"]:
            answer = str(variant.get("answer") or "")
            if variant.get("language") == wanted and answer:
                return answer
            if variant.get("language") == "ar":
                fallback = answer
            elif not fallback:
                fallback = answer
    return fallback


def _doc_ids(qa_id: str) -> dict[str, str]:
    keys = ("en", "ar", "fr", "franco", "en_core", "ar_core", "fr_core", "franco_core")
    values = ("en", "ar", "fr", "franco", "en-core", "ar-core", "fr-core", "franco-core")
    return {key: f"owner-qa-{qa_id}-{suffix}" for key, suffix in zip(keys, values, strict=True)}


def delete_qa(qa_id: str) -> bool:
    item_id = (qa_id or "").strip()
    if not item_id:
        return False
    ids = _doc_ids(item_id)
    with _session() as session:
        if session is None:
            return False
        found = session.execute(text("SELECT 1 FROM owner_copilot_qa WHERE id = :id"), {"id": item_id}).first()
        if found is None:
            return False
        session.execute(text("DELETE FROM owner_copilot_qa_variants WHERE qa_id = :id"), {"id": item_id})
        session.execute(text("DELETE FROM owner_copilot_qa WHERE id = :id"), {"id": item_id})
        session.execute(
            text(
                """
                DELETE FROM customer_ai_search_documents
                WHERE source_family = 'owner_qa'
                  AND (
                    parent_id = :id OR id = :en OR id = :ar OR id = :fr OR id = :franco
                    OR id = :en_core OR id = :ar_core OR id = :fr_core OR id = :franco_core
                  )
                """
            ),
            {"id": item_id, **ids},
        )
        session.commit()
    return True


def reindex_saved_qa() -> int:
    count = 0
    for group in list_qa():
        _index(str(group["id"]), list(group.get("variants") or []))
        count += 1
    return count


_REINDEXED = False


def ensure_reindexed() -> None:
    global _REINDEXED
    if _REINDEXED:
        return
    _REINDEXED = True
    try:
        with _session() as session:
            locked = True
            if session is not None:
                locked = bool(session.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _LOCK}).scalar())
            if not locked:
                return
            try:
                from services.owner_portal.embed_jobs import drain_embed_jobs

                drain_embed_jobs()
                reindex_saved_qa()
            finally:
                if session is not None:
                    session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK})
    except Exception:
        logger.exception("owner qa reindex failed")


def _entity_relation(question: str, bank_text: str) -> str:
    query_entities = {match.group(0).lower() for match in _ENTITY.finditer(question or "")}
    bank_entities = {match.group(0).lower() for match in _ENTITY.finditer(bank_text or "")}
    if query_entities and bank_entities and not query_entities <= bank_entities:
        return "conflict"
    if query_entities & bank_entities:
        return "share"
    words = set(re.findall(r"[a-z0-9]+", (question or "").lower()))
    for entity in bank_entities:
        parts = [part for part in entity.split("-") if part]
        if len(parts) >= 2 and all(part in words for part in parts):
            return "share"
    return "none"


def match_owner_qa(question: str, language: str) -> dict[str, Any] | None:
    ensure_reindexed()
    groups = list_qa()
    live = {str(group["id"]) for group in groups}
    needle = _norm(question)
    if not needle:
        return None
    for group in groups:
        for variant in group["variants"]:
            stored = {_norm(form) for form in search_forms(str(variant.get("question") or ""))}
            if needle in stored:
                answer = _answer_for(group["id"], language)
                if answer:
                    return {"qa_id": group["id"], "answer": answer, "score": 1.0, "hit": "exact"}
    from services.brain.search.store import query_similar

    best: dict[str, float] = {}
    for form in query_forms(question):
        vector = embed_one(form, query=True)
        if not vector:
            continue
        with _session() as session:
            found = query_similar(
                session,
                tenant_id=OWNER_KB_TENANT,
                space_id=ENTITY_DOCUMENT.space_id,
                vector=vector,
                families={_FAMILY},
                limit=8,
            )
        for item in found.items:
            qa_id = item.source_id.split(":", 1)[0]
            if qa_id not in live:
                continue
            best[qa_id] = max(best.get(qa_id, 0.0), float(item.score))
    if not best:
        return None
    ranked = sorted(best.items(), key=lambda pair: -pair[1])
    logger.info("owner qa candidates %s", [(qa_id, round(score, 4)) for qa_id, score in ranked[:3]])
    top_id, top_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if top_score - second < _MARGIN:
        return None
    bank = " ".join(
        str(variant.get("question") or "") for group in groups if group["id"] == top_id for variant in group["variants"]
    )
    relation = _entity_relation(question, bank)
    if relation == "conflict":
        return None
    cutoff = _ENTITY_THRESHOLD if relation == "share" else _THRESHOLD
    if top_score < cutoff:
        return None
    answer = _answer_for(top_id, language)
    if not answer:
        return None
    return {"qa_id": top_id, "answer": answer, "score": top_score, "hit": "semantic"}
