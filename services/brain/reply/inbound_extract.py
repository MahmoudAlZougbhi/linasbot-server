"""Bounded PDF/TXT/DOCX extract for customer inbound files (no owner-copilot coupling)."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile

MAX_EXTRACT_CHARS = 20_000
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_TEXT_MIME = frozenset(
    {
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/comma-separated-values",
        "application/json",
        "application/jsonl",
    }
)


def extract_inbound_file(*, data: bytes, mime: str, filename: str) -> dict[str, str]:
    kind = (mime or "").strip().lower()
    name = (filename or "file").strip() or "file"
    if kind in _TEXT_MIME or kind.startswith("text/") or name.lower().endswith((".txt", ".md", ".csv", ".json")):
        body = data.decode("utf-8", errors="replace")[:MAX_EXTRACT_CHARS]
        return {"status": "extracted", "text": body, "kind": "text"}
    if kind == "application/pdf" or name.lower().endswith(".pdf"):
        body = _pdf_text(data)
        return {"status": "extracted" if body else "empty_pdf", "text": body, "kind": "pdf"}
    if kind == _DOCX or name.lower().endswith(".docx"):
        body = _docx_text(data)
        return {"status": "extracted" if body else "empty_docx", "text": body, "kind": "docx"}
    return {"status": "unsupported_file_type", "text": "", "kind": "file"}


def _pdf_unescape(raw: bytes) -> str:
    text = raw.replace(b"\\n", b"\n").replace(b"\\r", b"\r").replace(b"\\t", b"\t")
    text = text.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
    return text.decode("latin-1", errors="replace")


def _pdf_text(data: bytes) -> str:
    chunks: list[str] = []
    for m in re.finditer(rb"\((?:\\.|[^\\)]){1,800}\)\s*Tj", data):
        inner = m.group(0)[1 : m.group(0).rfind(b")")]
        piece = _pdf_unescape(inner).strip()
        if piece:
            chunks.append(piece)
    return "\n".join(chunks).strip()[:MAX_EXTRACT_CHARS]


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml")
    except Exception:
        return ""
    root = ET.fromstring(xml)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    bits = [str(el.text) for el in root.iter(f"{ns}t") if el.text]
    return "\n".join(bits)[:MAX_EXTRACT_CHARS]
