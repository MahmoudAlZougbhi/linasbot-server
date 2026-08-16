"""Versioned Published CM manifest for Retrieval Luna (fixed vs selectable)."""

from __future__ import annotations

import time
from typing import Any

from services.cm.constants import CM_SECTIONS
from services.cm.version_store import PublishedVersionError, load_published_content, read_version_manifest
from services.customer_reply_v2.models import ManifestSection

# Full AI Basics / Style are Answer-only; never selectable by Retrieval Luna.
# Comment AI-guidance rules ARE selectable. They are reply-surface guidance, not
# business knowledge — Luna must still retrieve services/locations/hours/products.
FIXED_ANSWER_SECTIONS = frozenset({"ai_basics", "style"})
NON_SELECTABLE_SECTIONS: frozenset[str] = frozenset()

SECTION_DESCRIPTIONS: dict[str, str] = {
    "ai_basics": "Business identity and assistant personality (fixed Answer context).",
    "languages": "Supported languages and response-language policy.",
    "style": "Tone, formality, and reply style rules (fixed Answer context).",
    "dynamic_messages": "Configured dynamic system messages.",
    "services": "Catalog of services or products.",
    "branches": "Locations, addresses, and hours.",
    "prices": "Prices, currencies, and offers.",
    "care": "Pre/post care instructions.",
    "knowledge": "Long-form knowledge articles.",
    "faq": "Published FAQ pairs (also used by FAQ fast path).",
    "handoff": "Human/WhatsApp handoff destinations (server-enforced).",
    "restricted": "Restricted topics that must be refused (server-enforced).",
    "actions": "Allowed AI actions / capability gates.",
    "comments": "AI-guidance Comment Rules: how to reply on comments (short/public, continue in DM). Not business knowledge. Always also retrieve services, locations, hours, prices, products, knowledge, and request definitions when the comment asks about them.",
    "ai_limits": "AI usage and behavior limits.",
    "off_days": "Closed days and holiday schedules.",
    "opening_hours": "Named opening-hour calendars.",
    "requests_appointments": "Customer request rules: appointment, order, or other (title + note).",
}

_CACHE: dict[str, tuple[float, str, list[ManifestSection]]] = {}
_CACHE_TTL_SECONDS = 60.0


def _item_count(section_id: str, payload: dict[str, Any]) -> int:
    if section_id in FIXED_ANSWER_SECTIONS:
        return 0
    items = payload.get("items")
    if isinstance(items, list):
        return len(items)
    rules = payload.get("rules")
    if isinstance(rules, list):
        return len(rules)
    topics = payload.get("topics")
    if isinstance(topics, list):
        return len(topics)
    contacts = payload.get("contacts")
    if isinstance(contacts, list):
        return len(contacts)
    matrix = payload.get("matrix")
    if isinstance(matrix, list):
        return len(matrix)
    # off_days / ai_limits shaped objects
    if section_id == "off_days":
        days = payload.get("days") or payload.get("specific_days") or []
        return len(days) if isinstance(days, list) else 1 if payload else 0
    return 1 if payload else 0


def build_published_manifest(tenant_id: str) -> tuple[str, list[ManifestSection]]:
    """Build dynamic manifest from Published CM only. Raises PublishedVersionError."""
    pointer, sections = load_published_content(tenant_id)
    revision = pointer.content_version_id
    # Prefer stored version manifest section order when present; always cover CM_SECTIONS.
    stored = read_version_manifest(tenant_id, revision) or {}
    order = list(stored.get("sections") or []) if isinstance(stored.get("sections"), list) else []
    ordered_ids: list[str] = []
    for sid in order:
        if isinstance(sid, str) and sid in CM_SECTIONS and sid not in ordered_ids:
            ordered_ids.append(sid)
    for sid in CM_SECTIONS:
        if sid not in ordered_ids:
            ordered_ids.append(sid)

    manifest: list[ManifestSection] = []
    for section_id in ordered_ids:
        payload = sections.get(section_id) or {}
        fixed = section_id in FIXED_ANSWER_SECTIONS
        selectable = not fixed and section_id not in NON_SELECTABLE_SECTIONS
        manifest.append(
            ManifestSection(
                section_id=section_id,
                name=section_id.replace("_", " ").title(),
                description=SECTION_DESCRIPTIONS.get(section_id, f"Published CM section {section_id}."),
                published_revision=revision,
                item_count=_item_count(section_id, payload if isinstance(payload, dict) else {}),
                fixed_answer_context=fixed,
                selectable=selectable,
            )
        )
    return revision, manifest


def get_cached_manifest(tenant_id: str) -> tuple[str, list[ManifestSection]]:
    """Tenant+revision keyed cache; invalidated when published revision changes."""
    now = time.time()
    cached = _CACHE.get(tenant_id)
    if cached is not None:
        ts, rev, items = cached
        if now - ts < _CACHE_TTL_SECONDS:
            # Cheap revision check via pointer without full content reload when possible
            try:
                from services.cm.version_store import read_published_pointer

                pointer = read_published_pointer(tenant_id)
                if pointer and pointer.content_version_id == rev:
                    return rev, items
            except Exception:
                pass
    revision, items = build_published_manifest(tenant_id)
    _CACHE[tenant_id] = (now, revision, items)
    return revision, items


def clear_manifest_cache(tenant_id: str | None = None) -> None:
    if tenant_id is None:
        _CACHE.clear()
    else:
        _CACHE.pop(tenant_id, None)


def manifest_for_retrieval_luna(tenant_id: str) -> dict[str, Any]:
    """Safe JSON for Retrieval Luna — no full AI Basics/Style bodies."""
    revision, sections = get_cached_manifest(tenant_id)
    return {
        "published_revision": revision,
        "sections": [
            {
                "section_id": s.section_id,
                "name": s.name,
                "description": s.description,
                "item_count": s.item_count,
                "fixed_answer_context": s.fixed_answer_context,
                "selectable": s.selectable,
            }
            for s in sections
        ],
    }


def load_fixed_answer_context(tenant_id: str) -> dict[str, Any]:
    """Full Published AI Basics + Style + Languages for Answer Tera only."""
    pointer, sections = load_published_content(tenant_id)
    return {
        "published_revision": pointer.content_version_id,
        "ai_basics": sections.get("ai_basics") or {},
        "style": sections.get("style") or {},
        "languages": sections.get("languages") or {},
    }


def assert_published_only(tenant_id: str) -> str:
    """Return published revision or raise — Draft is never loaded."""
    try:
        revision, _ = get_cached_manifest(tenant_id)
        return revision
    except PublishedVersionError:
        raise
