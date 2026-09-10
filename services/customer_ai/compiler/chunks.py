"""Heading-aware Knowledge chunks for voyage-context-4 groups."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6}\s+|[A-Z][A-Z0-9 /-]{3,}:)\s*(.*)$")


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    parent_id: str
    heading: str
    text: str


def chunk_document(*, document_id: str, body: str, max_chars: int = 1200) -> list[KnowledgeChunk]:
    text = (body or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    blocks: list[tuple[str, list[str]]] = [("", [])]
    for line in text.split("\n"):
        match = _HEADING.match(line.strip())
        if match:
            heading = (match.group(2) or line).strip()
            blocks.append((heading, []))
            continue
        blocks[-1][1].append(line)
    chunks: list[KnowledgeChunk] = []
    index = 0
    for heading, lines in blocks:
        buf = "\n".join(lines).strip()
        if not buf and not heading:
            continue
        pieces = [buf] if len(buf) <= max_chars else [buf[i : i + max_chars] for i in range(0, len(buf), max_chars)]
        for piece in pieces:
            index += 1
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{document_id}:c{index}",
                    parent_id=document_id,
                    heading=heading,
                    text="\n".join(p for p in (heading, piece) if p).strip(),
                )
            )
    return chunks


def contextual_groups(chunks: list[KnowledgeChunk]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for chunk in chunks:
        groups.setdefault(chunk.parent_id, []).append(chunk.text)
    return groups
