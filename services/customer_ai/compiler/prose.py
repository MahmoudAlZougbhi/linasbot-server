"""Which CM fields are large free text that Luna should chunk."""

from __future__ import annotations

from typing import Any

# Knowledge/care files are always chunked on first save (any non-empty body).
ALWAYS_CHUNK_SECTIONS = frozenset({"knowledge", "care"})
# Other sections: only when the owner wrote a long note/description/body.
LARGE_TEXT_SECTIONS = frozenset(
    {
        "knowledge",
        "care",
        "branches",
        "opening_hours",
        "prices",
        "services",
        "requests_appointments",
        "dynamic_messages",
        "ai_basics",
        "style",
    }
)
LARGE_TEXT_MIN_CHARS = 280
SECTION_ITEM_ID = "_section"
POLICY_ITEM_ID = "_policy"


def _text(raw: Any) -> str:
    return " ".join(str(raw or "").split()).strip()


def _day_notes(weekly: Any) -> list[str]:
    if not isinstance(weekly, dict):
        return []
    notes: list[str] = []
    for value in weekly.values():
        if isinstance(value, dict):
            note = _text(value.get("note") or value.get("notes"))
            if note:
                notes.append(note)
    return notes


def extract_prose(section: str, raw: dict[str, Any] | None) -> str:
    """Owner-authored prose only — clocks, ids, and prices are not chunked alone."""
    item = raw if isinstance(raw, dict) else {}
    name = (section or "").strip()
    bits: list[str] = []
    if name in {"knowledge", "care"}:
        bits.extend([_text(item.get("title")), _text(item.get("body")), _text(item.get("notes"))])
    elif name == "branches":
        bits.extend(
            [
                _text(item.get("notes")),
                _text(item.get("policy_text")),
                *_day_notes(item.get("weekly_schedule")),
            ]
        )
    elif name == "opening_hours":
        bits.append(_text(item.get("notes")))
    elif name in {"prices", "services"}:
        bits.extend(
            [
                _text(item.get("description")),
                _text(item.get("notes")),
                _text(item.get("policy_text")),
            ]
        )
    elif name == "requests_appointments":
        bits.extend([_text(item.get("name")), _text(item.get("notes"))])
    elif name == "dynamic_messages":
        bits.extend(
            [
                _text(item.get("name") or item.get("title")),
                _text(item.get("notes")),
                _text(item.get("en")),
                _text(item.get("ar")),
                _text(item.get("fr")),
            ]
        )
    elif name == "ai_basics":
        bits.extend(
            [
                _text(item.get("identity_summary")),
                _text(item.get("short_introduction")),
                _text(item.get("greeting_behavior")),
                _text(item.get("advanced_instructions")),
                _text(item.get("business_purpose")),
                _text(item.get("notes")),
            ]
        )
    elif name == "style":
        examples = item.get("example_replies")
        extra = " ".join(_text(x) for x in examples) if isinstance(examples, list) else ""
        bits.extend([_text(item.get("style_body")), _text(item.get("notes")), extra])
    return "\n\n".join(b for b in bits if b)


def needs_luna_chunks(section: str, raw: dict[str, Any] | None) -> bool:
    name = (section or "").strip()
    if name not in LARGE_TEXT_SECTIONS:
        return False
    item = raw if isinstance(raw, dict) else {}
    if name == "requests_appointments":
        notes = _text(item.get("notes"))
        return len(notes) >= LARGE_TEXT_MIN_CHARS
    prose = extract_prose(name, item)
    if not prose:
        return False
    if name in ALWAYS_CHUNK_SECTIONS:
        return True
    return len(prose) >= LARGE_TEXT_MIN_CHARS
