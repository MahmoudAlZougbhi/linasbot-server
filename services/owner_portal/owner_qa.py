"""Owner copilot Q&A. A close match answers with no model call."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from services.brain.providers.spaces import ENTITY_DOCUMENT
from services.owner_portal.owner_embed import embed_one
from services.owner_portal.owner_kb_store import OWNER_KB_TENANT, _session

logger = logging.getLogger(__name__)

_FAMILY = "owner_qa"
# Cross-lingual cosine on the Voyage entity model sits around 0.75–0.80.
# 0.90 only kept exact duplicates. Unrelated questions stay well below 0.75.
_THRESHOLD = 0.75
_LANGS = ("ar", "en", "fr", "franco")


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


def _index(qa_id: str, rows: list[dict[str, str]]) -> None:
    from services.brain.search.store import write_documents

    docs: list[dict[str, Any]] = []
    vectors: list[list[float]] = []
    for row in rows:
        vector = embed_one(row["question"], query=False)
        if not vector:
            logger.warning("owner qa variant %s/%s was not embedded", qa_id, row["language"])
            continue
        docs.append(
            {
                "id": f"owner-qa-{qa_id}-{row['language']}",
                "tenant_id": OWNER_KB_TENANT,
                "space_id": ENTITY_DOCUMENT.space_id,
                "source_family": _FAMILY,
                "source_id": f"{qa_id}:{row['language']}",
                "chunk_id": row["language"],
                "parent_id": qa_id,
                "index_version": "",
                "source_revision": "1",
                "content_hash": qa_id + row["language"],
                "title": row["answer"][:200],
                "search_text": row["question"],
                "visible": True,
            }
        )
        vectors.append(vector)
    if not docs:
        return
    with _session() as session:
        write_documents(session, docs, vectors)
        if session is not None:
            session.commit()


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


def match_owner_qa(question: str, language: str) -> dict[str, Any] | None:
    needle = _norm(question)
    if not needle:
        return None
    for group in list_qa():
        for variant in group["variants"]:
            if _norm(variant["question"]) == needle:
                answer = _answer_for(group["id"], language)
                if answer:
                    return {"qa_id": group["id"], "answer": answer, "score": 1.0, "hit": "exact"}
    from services.brain.search.store import query_similar

    vector = embed_one(question, query=True)
    if not vector:
        return None
    with _session() as session:
        found = query_similar(
            session,
            tenant_id=OWNER_KB_TENANT,
            space_id=ENTITY_DOCUMENT.space_id,
            vector=vector,
            families={_FAMILY},
            limit=3,
        )
    top = found.items[0].score if found.items else None
    logger.info("owner qa top score %s threshold %s", top, _THRESHOLD)
    if top is None or top < _THRESHOLD:
        return None
    source = found.items[0].source_id
    qa_id = source.split(":", 1)[0]
    answer = _answer_for(qa_id, language)
    if not answer:
        return None
    return {"qa_id": qa_id, "answer": answer, "score": found.items[0].score, "hit": "semantic"}
