"""Pack stored owner attachments into the chat user message so Sol sees file bytes."""

from __future__ import annotations

import base64
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

from services.owner_copilot_v2.attachments import load_attachment_bytes, load_attachment_meta

MAX_TEXT_CHARS = 80_000
MAX_INLINE_IMAGE_BYTES = 2_500_000

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
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def user_content_with_attachments(
    *,
    tenant_id: str,
    user_text: str,
    attachment_ids: list[str],
) -> str | list[dict[str, Any]]:
    """Return chat.completions user content: text plus image_url parts when needed."""
    text_chunks = [user_text.strip()] if user_text.strip() else []
    image_parts: list[dict[str, Any]] = []
    for aid in attachment_ids:
        packed = _pack_one(tenant_id=tenant_id, attachment_id=aid)
        if packed.get("text"):
            text_chunks.append(str(packed["text"]))
        if packed.get("image_url"):
            image_parts.append({"type": "image_url", "image_url": {"url": str(packed["image_url"])}})
    joined = "\n\n".join(t for t in text_chunks if t) or "Please analyze this attachment."
    if not image_parts:
        return joined
    return [{"type": "text", "text": joined}, *image_parts]


def _pack_one(*, tenant_id: str, attachment_id: str) -> dict[str, str]:
    meta = load_attachment_meta(tenant_id=tenant_id, attachment_id=attachment_id)
    raw = load_attachment_bytes(tenant_id=tenant_id, attachment_id=attachment_id)
    if not meta or raw is None:
        return {"text": f"[Attached file {attachment_id} could not be loaded.]"}
    mime = str(meta.get("mime") or "")
    name = str(meta.get("filename") or attachment_id)
    header = f"[Attached file: {name} ({mime}) id={attachment_id}]"
    if mime.startswith("image/"):
        if len(raw) > MAX_INLINE_IMAGE_BYTES:
            return {"text": f"{header}\nImage is stored; too large to inline. Use extract_price_list if needed."}
        b64 = base64.b64encode(raw).decode("ascii")
        return {"text": header, "image_url": f"data:{mime};base64,{b64}"}
    if mime in _TEXT_MIME or mime.startswith("text/"):
        body = raw.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
        return {"text": f"{header}\n{body}"}
    if mime == "application/pdf":
        extracted = _pdf_text(raw)
        return {"text": f"{header}\n{extracted}" if extracted else header}
    if mime == _DOCX:
        extracted = _docx_text(raw)
        return {"text": f"{header}\n{extracted}" if extracted else header}
    if mime == _XLSX:
        extracted = _xlsx_text(raw)
        return {"text": f"{header}\n{extracted}" if extracted else header}
    return {"text": header}


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
    joined = "\n".join(chunks).strip()
    return joined[:MAX_TEXT_CHARS]


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml")
    except Exception:
        return ""
    root = ET.fromstring(xml)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    bits = [str(el.text) for el in root.iter(f"{ns}t") if el.text]
    return "\n".join(bits)[:MAX_TEXT_CHARS]


def _xlsx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "xl/sharedStrings.xml" not in names:
                return ""
            xml = zf.read("xl/sharedStrings.xml")
    except Exception:
        return ""
    root = ET.fromstring(xml)
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    bits = [str(el.text) for el in root.iter(f"{ns}t") if el.text]
    return "\n".join(bits)[:MAX_TEXT_CHARS]
