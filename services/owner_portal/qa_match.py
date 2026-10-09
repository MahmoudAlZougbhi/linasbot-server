"""One Q&A answer picker for the stream and the lab."""

from __future__ import annotations


def answer_language(language: str) -> str:
    code = (language or "").strip().lower()
    if code == "franco":
        return "franco"
    if code in {"ar", "en", "fr"}:
        return code
    return "en"


def pick_variant(variants: list[dict[str, str]], language: str) -> str:
    wanted = answer_language(language)
    by_lang = {str(row.get("language") or ""): str(row.get("answer") or "") for row in variants}
    if by_lang.get(wanted):
        return by_lang[wanted]
    if wanted == "franco" and by_lang.get("en"):
        return by_lang["en"]
    return by_lang.get("en") or ""
