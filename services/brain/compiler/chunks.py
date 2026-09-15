"""Save-time Luna chunk rows with explicit raw vs contextual text."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CONTEXTUALIZATION_VERSION = "customer_ai.context.v1"


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    parent_id: str
    heading: str
    raw_text: str
    contextualized_text: str
    text: str  # backwards-compatible alias of contextualized_text for groups
    section: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _context_prefix(
    *,
    document_title: str,
    heading: str,
    entity: str,
    branch: str,
    source_family: str,
    tenant_id: str,
) -> str:
    bits = [
        f"Document: {document_title}" if document_title else "",
        f"Section: {heading}" if heading else "",
        f"Entity: {entity}" if entity else "",
        f"Branch: {branch}" if branch else "",
        f"Family: {source_family}" if source_family else "",
        f"Tenant: {tenant_id}" if tenant_id else "",
    ]
    return " | ".join(b for b in bits if b)


def chunks_from_texts(
    *,
    document_id: str,
    texts: list[str] | tuple[str, ...],
    document_title: str = "",
    entity: str = "",
    branch: str = "",
    source_family: str = "knowledge",
    tenant_id: str = "",
    source_version: str = "",
    page: str = "",
) -> list[KnowledgeChunk]:
    """Build KnowledgeChunk rows from save-time sidecar texts (no mechanical re-slice)."""
    title = (document_title or "").strip() or document_id
    chunks: list[KnowledgeChunk] = []
    for index, blob in enumerate(texts, 1):
        raw = str(blob or "").strip()
        if not raw:
            continue
        heading = ""
        first, _, rest = raw.partition("\n")
        if rest.strip() and len(first.strip()) <= 120:
            heading = first.strip()
        prefix = _context_prefix(
            document_title=title,
            heading=heading,
            entity=entity,
            branch=branch,
            source_family=source_family,
            tenant_id=tenant_id,
        )
        contextual = f"{prefix}\n{raw}".strip() if prefix else raw
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"{document_id}:c{index}",
                parent_id=document_id,
                heading=heading,
                raw_text=raw,
                contextualized_text=contextual,
                text=contextual,
                section=heading,
                metadata={
                    "document_id": document_id,
                    "document_title": title,
                    "entity": entity,
                    "branch": branch,
                    "source_family": source_family,
                    "tenant_id": tenant_id,
                    "source_version": source_version,
                    "page": page,
                    "contextualization_version": CONTEXTUALIZATION_VERSION,
                },
            )
        )
    return chunks


def contextual_groups(chunks: list[KnowledgeChunk]) -> dict[str, list[str]]:
    """Group contextualized chunk texts by parent document for voyage-context-4."""
    groups: dict[str, list[str]] = {}
    for chunk in chunks:
        groups.setdefault(chunk.parent_id, []).append(chunk.contextualized_text or chunk.text)
    return groups


def raw_groups(chunks: list[KnowledgeChunk]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for chunk in chunks:
        groups.setdefault(chunk.parent_id, []).append(chunk.raw_text or chunk.text)
    return groups
