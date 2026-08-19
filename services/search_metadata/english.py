"""English-only checks for internal Luna search metadata.

Rejects non-Latin scripts and common Latin-script non-English (French, Spanish,
German, Italian). Search metadata is internal; original user content is unchanged.
"""

from __future__ import annotations

import re
import unicodedata

_NON_ENGLISH_SCRIPT = re.compile(
    r"[\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF"
    r"\u0900-\u097F\u0E00-\u0E7F\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF]"
)

# Distinctive Latin-script words that must not remain in internal metadata.
_STRONG_MARKERS = frozenset(
    {
        "horaires",
        "horaire",
        "ouverture",
        "sucursale",
        "succursale",
        "contient",
        "rendez-vous",
        "aujourdhui",
        "fermee",
        "ferme",
        "magasin",
        "boutique",
        "sucursal",
        "contiene",
        "cerrado",
        "abierto",
        "tienda",
        "apertura",
        "offnungszeiten",
        "oeffnungszeiten",
        "filiale",
        "enthalt",
        "geschlossen",
        "wochentag",
        "orari",
        "chiuso",
        "aperto",
        "questa",
        "aquest",
        "bei",
        "nicht",
        "avec",
        "cette",
        "esta",
        "este",
        "della",
        "delle",
        "questo",
        "pour",
        "para",
        "fuer",
        "für",
        "und",
        "los",
        "las",
        "der",
        "das",
        "les",
        "une",
        "des",
        "del",
        "el",
    }
)

_WEAK_MARKERS = frozenset({"la", "le", "de", "du", "en", "un", "una", "die", "mit", "per", "di"})

_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?")


def contains_non_english_script(text: str) -> bool:
    return bool(_NON_ENGLISH_SCRIPT.search(text or ""))


def _folded_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
    ascii_text = ascii_text.replace("ß", "ss").replace("'", "").replace("'", "")
    return _TOKEN.findall(ascii_text)


def looks_like_english(text: str) -> bool:
    """True when compact metadata is English (not merely Latin-script)."""
    value = " ".join(str(text or "").split())
    if not value or contains_non_english_script(value):
        return False
    tokens = _folded_tokens(value)
    if not tokens:
        return False
    strong = [tok for tok in tokens if tok in _STRONG_MARKERS]
    if strong:
        return False
    weak = [tok for tok in tokens if tok in _WEAK_MARKERS]
    if len(weak) >= 2:
        return False
    return True


def english_only_or_empty(text: str, *, require_english_language: bool = True) -> str:
    """Keep compact English text; otherwise return empty (caller keeps original user fields)."""
    value = " ".join(str(text or "").split())
    if not value or contains_non_english_script(value):
        return ""
    if require_english_language and not looks_like_english(value):
        return ""
    return value
