"""Tenant-scoped semantic index over FAQ + Knowledge/Care content (plan §9 / §13.1 / D11).

Built from CM section payloads (draft for Lab preview, or a published version's content at
publish time). Index files live only under ``{DATA_ROOT}/tenants/{tenant_id}/cm/indexes/``.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from services.cm.atomic_io import atomic_write_json, read_json, read_json_object
from services.cm.constants import cm_runtime_mode
from services.cm.embeddings import (
    assert_published_embedding_pin,
    cosine_similarity,
    embed_texts,
    embedding_pin,
)
from services.cm.paths import indexes_dir
from services.cm.schemas import CareSection, FaqSection, KnowledgeSection

INDEX_MANIFEST_FILE = "manifest.json"
INDEX_VECTORS_FILE = "vectors.json"
_PROVENANCE_PREFIX = "--- redistributed from "
# Stay well under OpenAI embedding input limit (8192 tokens).
_MAX_EMBED_CHARS = 24_000

_RawEntry = tuple[str, str, str, str, dict[str, Any]]  # source_id, kind, language, text, metadata


def _chunk_policy_text(policy: str) -> list[str]:
    """Split redistributed policy blobs so embed calls stay under token limits."""
    text = policy.strip()
    if not text:
        return []
    if _PROVENANCE_PREFIX in text:
        parts = re.split(rf"(?={re.escape(_PROVENANCE_PREFIX)})", text)
        chunks = [part.strip() for part in parts if part.strip()]
    else:
        chunks = [text]
    out: list[str] = []
    for chunk in chunks:
        if len(chunk) <= _MAX_EMBED_CHARS:
            out.append(chunk)
            continue
        start = 0
        while start < len(chunk):
            out.append(chunk[start : start + _MAX_EMBED_CHARS])
            start += _MAX_EMBED_CHARS
    return out


def _faq_entries(payload: dict[str, Any] | None) -> list[_RawEntry]:
    out: list[_RawEntry] = []
    if not payload:
        return out
    section = FaqSection.model_validate(payload)
    for item in section.items:
        if item.status in {"archived", "restricted"}:
            continue
        for variant in item.variants:
            if not variant.question:
                continue
            source_id = f"faq:{item.qa_group_id}:{variant.language}"
            out.append(
                (
                    source_id,
                    "faq",
                    variant.language,
                    variant.question,
                    {"qa_group_id": item.qa_group_id, "answer": variant.answer, "tags": list(item.tags)},
                )
            )
    return out


def _article_entries(payload: dict[str, Any] | None, kind: str) -> list[_RawEntry]:
    out: list[_RawEntry] = []
    if not payload:
        return out
    model_cls: type[KnowledgeSection] | type[CareSection] = KnowledgeSection if kind == "knowledge" else CareSection
    section = model_cls.model_validate(payload)
    for item in section.items:
        if item.status in {"archived", "restricted"}:
            continue
        text = f"{item.title}\n{item.body}".strip()
        if not text:
            continue
        source_id = f"{kind}:{item.id}"
        out.append((source_id, kind, item.language or "", text, {"title": item.title, "tags": list(item.tags)}))
    return out


def _section_notes_entries(section_name: str, payload: dict[str, Any] | None) -> list[_RawEntry]:
    """Index redistributed policy text moved out of Knowledge (branches/handoff/prices)."""
    out: list[_RawEntry] = []
    if not payload or not isinstance(payload, dict):
        return out
    policy = payload.get("policy_text")
    if not isinstance(policy, str) or not policy.strip():
        return out
    for idx, chunk in enumerate(_chunk_policy_text(policy)):
        out.append(
            (
                f"{section_name}:policy_text:{idx}",
                section_name,
                "",
                chunk,
                {"title": f"{section_name} policy", "tags": ["section_policy", "cm_redistributed"], "chunk": idx},
            )
        )
    return out


async def build_index(
    *,
    tenant_id: str,
    content_version_id: str,
    sections: dict[str, dict[str, Any]],
    index_id: str | None = None,
) -> dict[str, Any]:
    """Build and persist a semantic index over FAQ + Knowledge + Care + redistributed notes."""
    entries: list[_RawEntry] = [
        *_faq_entries(sections.get("faq")),
        *_article_entries(sections.get("knowledge"), "knowledge"),
        *_article_entries(sections.get("care"), "care"),
        *_section_notes_entries("branches", sections.get("branches")),
        *_section_notes_entries("handoff", sections.get("handoff")),
        *_section_notes_entries("prices", sections.get("prices")),
    ]

    texts = [text for _, _, _, text, _ in entries]
    vectors = await embed_texts(texts)
    pin = embedding_pin()
    resolved_index_id = index_id or f"idx_{uuid.uuid4().hex[:12]}"

    vector_rows = [
        {
            "source_id": source_id,
            "kind": kind,
            "language": language,
            "text": text,
            "vector": vector,
            "metadata": metadata,
        }
        for (source_id, kind, language, text, metadata), vector in zip(entries, vectors, strict=True)
    ]

    manifest = {
        "index_id": resolved_index_id,
        "tenant_id": tenant_id,
        "content_version_id": content_version_id,
        "entry_count": len(vector_rows),
        "embedding": pin.as_dict(),
    }

    index_root = indexes_dir(tenant_id) / resolved_index_id
    atomic_write_json(index_root / INDEX_MANIFEST_FILE, manifest)
    atomic_write_json(index_root / INDEX_VECTORS_FILE, vector_rows)
    return manifest


def index_exists(tenant_id: str, index_id: str) -> bool:
    index_root = indexes_dir(tenant_id) / index_id
    return (index_root / INDEX_MANIFEST_FILE).exists() and (index_root / INDEX_VECTORS_FILE).exists()


def load_index(tenant_id: str, index_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    index_root = indexes_dir(tenant_id) / index_id
    manifest = read_json_object(index_root / INDEX_MANIFEST_FILE)
    rows = read_json(index_root / INDEX_VECTORS_FILE)
    if not isinstance(rows, list):
        raise ValueError(f"Corrupt semantic index vectors for tenant={tenant_id!r} index={index_id!r}")
    typed_rows: list[dict[str, Any]] = [row for row in rows if isinstance(row, dict)]
    return manifest, typed_rows


async def search(
    *,
    tenant_id: str,
    index_id: str,
    query: str,
    kind: str | None = None,
    language: str | None = None,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Cosine top-k search, tenant + index scoped. Returns rows without raw vectors."""
    manifest, rows = load_index(tenant_id, index_id)
    if cm_runtime_mode() == "published":
        embedding_raw = manifest.get("embedding")
        embedding: dict[str, Any] = embedding_raw if isinstance(embedding_raw, dict) else {}
        provider = str(embedding.get("provider") or "")
        assert_published_embedding_pin(provider, context=f"index {index_id}")
    if not rows or not (query or "").strip():
        return []

    query_vectors = await embed_texts([query])
    query_vector = query_vectors[0] if query_vectors else []

    scored: list[dict[str, Any]] = []
    for row in rows:
        if kind and row.get("kind") != kind:
            continue
        if language and row.get("language") and row.get("language") != language:
            continue
        score = cosine_similarity(query_vector, row.get("vector") or [])
        result = {k: v for k, v in row.items() if k != "vector"}
        result["score"] = score
        scored.append(result)

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k]
