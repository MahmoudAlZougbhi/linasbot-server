"""Query normalization for Arabizi / typos without destroying numbers, phones, or URLs."""

from __future__ import annotations

import re
from typing import Any

from services.customer_ai.retrieve.normalize_ar import normalize_arabic

_PROTECTED = re.compile(
    r"("
    r"(?:https?://|www\.)[^\s<>\"'`]+"
    r"|\+?\d[\d\s\-().]{5,}\d"
    r"|\d+(?:[.,]\d+)?"
    r")",
    re.I,
)

_WORD_MAP: dict[str, str] = {
    "antelias": "antelias",
    "antelyas": "antelias",
    "antalias": "antelias",
    "antelyaas": "antelias",
    "3antelias": "antelias",
    "3ntelias": "antelias",
    "beirut": "beirut",
    "bayrut": "beirut",
    "beyrouth": "beirut",
    "beirout": "beirut",
    "beiruut": "beirut",
    "se3er": "سعر",
    "se3r": "سعر",
    "si3er": "سعر",
    "sa3er": "سعر",
    "su3r": "سعر",
    "price": "price",
    "prices": "price",
    "cost": "price",
    "howmuch": "price",
    "dawem": "دوام",
    "aw2at": "اوقات",
    "sha3er": "شعر",
    "fullbody": "full body",
}


def _protect(text: str) -> tuple[str, list[str]]:
    held: list[str] = []

    def _keep(match: re.Match[str]) -> str:
        held.append(match.group(0))
        return f" __N{len(held) - 1}__ "

    return _PROTECTED.sub(_keep, text or ""), held


def _restore(text: str, held: list[str]) -> str:
    out = text
    for index, value in enumerate(held):
        out = out.replace(f"__N{index}__", value)
    return " ".join(out.split())


def _map_tokens(text: str) -> str:
    parts: list[str] = []
    for token in re.split(r"(\s+)", text):
        if not token or token.isspace():
            parts.append(token)
            continue
        if token.startswith("__N") and token.endswith("__"):
            parts.append(token)
            continue
        key = re.sub(r"[^\w\u0600-\u06FF]+", "", token, flags=re.UNICODE).casefold()
        parts.append(_WORD_MAP.get(key, token))
    return "".join(parts)


def normalize_query(message: str) -> dict[str, Any]:
    """Return {original, primary, alternates} preserving numbers/phones/urls."""
    original = (message or "").strip()
    if not original:
        return {"original": "", "primary": "", "alternates": []}
    protected, held = _protect(original)
    primary = _restore(_map_tokens(protected), held)
    alternates: list[str] = []
    arab = normalize_arabic(primary)
    if arab and arab.casefold() != primary.casefold():
        alternates.append(arab)
    for src, dst in (("se3er", "سعر"), ("antelias", "antelias branch"), ("beirut", "beirut branch"), ("price", "سعر")):
        if re.search(rf"\b{re.escape(src)}\b", original, re.I):
            alt = f"{primary} {dst}".strip()
            if alt.casefold() != primary.casefold():
                alternates.append(alt)
    # High-uncertainty: keep original as an alternate search variant (never drop).
    if primary.casefold() != original.casefold():
        alternates.insert(0, original)
    seen = {primary.casefold()}
    unique: list[str] = []
    for item in alternates:
        key = item.casefold()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return {"original": original, "primary": primary or original, "alternates": unique}


# Back-compat alias used by earlier drafts.
normalize_query_variants = normalize_query
