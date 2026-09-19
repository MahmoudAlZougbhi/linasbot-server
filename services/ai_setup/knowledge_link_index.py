"""Published Knowledge/Care kind=link URLs as identity keys — not outbound spam."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from services.ai_setup.setup_resources import iter_published_source_items
from services.ai_setup.version_store import PublishedVersionError, load_published_content

_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'`]+", re.I)
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "gclsrc",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "igsh",
        "si",
        "feature",
        "ref",
        "ref_src",
        "mibextid",
        "spm",
    }
)
_LINK_SECTIONS = frozenset({"knowledge", "care"})


def extract_raw_urls(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _URL.finditer(text or ""):
        raw = match.group(0).rstrip(".,;:!?)]}\"'")
        key = raw.casefold()
        if raw and key not in seen:
            seen.add(key)
            found.append(raw)
    return found


def question_without_urls(text: str) -> str:
    stripped = _URL.sub(" ", text or "")
    return " ".join(stripped.split()).strip()


def normalize_knowledge_url(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    try:
        parts = urlsplit(text)
    except Exception:
        return ""
    host = (parts.hostname or "").lower().removeprefix("www.")
    if not host:
        return ""
    path = (parts.path or "").rstrip("/")
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith(_TRACKING_PREFIXES) or lowered in _TRACKING_KEYS:
            continue
        kept.append((lowered, value))
    kept.sort()
    query = urlencode(kept, doseq=True)
    return f"{host}{path}" + (f"?{query}" if query else "")


def _as_dict(raw: Any) -> dict[str, Any] | None:
    if hasattr(raw, "model_dump"):
        dumped = raw.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else None
    return raw if isinstance(raw, dict) else None


def index_published_knowledge_links(tenant_id: str) -> dict[str, dict[str, Any]]:
    """Map normalized URL → published knowledge/care identity (current revision)."""
    index: dict[str, dict[str, Any]] = {}
    if not (tenant_id or "").strip():
        return index
    try:
        pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return index
    except Exception:
        return index
    revision = str(getattr(pointer, "content_version_id", "") or getattr(pointer, "revision", "") or "")
    for source_id, item in iter_published_source_items(sections if isinstance(sections, dict) else {}):
        section_id = source_id.split(":", 1)[0]
        if section_id not in _LINK_SECTIONS:
            continue
        for att_raw in list(item.get("attachments") or []):
            att = _as_dict(att_raw)
            if att is None or str(att.get("kind") or "").strip().lower() != "link":
                continue
            if str(att.get("status") or "active").strip().lower() not in {"", "active"}:
                continue
            key = normalize_knowledge_url(str(att.get("url") or ""))
            if not key:
                continue
            index[key] = {
                "url_key": key,
                "resource_ref": str(att.get("id") or ""),
                "source_item_id": source_id,
                "source_section": section_id,
                "item_id": str(item.get("id") or item.get("qa_group_id") or source_id.split(":", 1)[-1]),
                "title": str(item.get("title") or item.get("name") or att.get("title") or ""),
                "body": str(item.get("body") or item.get("content") or item.get("description") or ""),
                "item": item,
                "revision": revision,
                "tenant_id": tenant_id,
            }
    return index


def find_knowledge_by_urls(*, tenant_id: str, urls: list[str]) -> list[dict[str, Any]]:
    index = index_published_knowledge_links(tenant_id)
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in urls:
        key = normalize_knowledge_url(raw)
        row = index.get(key)
        if row is None:
            continue
        sid = str(row.get("source_item_id") or "")
        if sid in seen:
            continue
        seen.add(sid)
        hits.append(row)
    return hits
