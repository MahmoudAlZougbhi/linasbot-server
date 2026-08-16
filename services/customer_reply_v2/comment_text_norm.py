"""Safe deterministic normalization for Comment Rule triggers (no LLM)."""

from __future__ import annotations

import re
import unicodedata

_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS = re.compile(r"\s+")
_ARABIC_MAP = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ـ": "",
    }
)


def normalize_comment_text(text: str) -> str:
    raw = unicodedata.normalize("NFKD", str(text or ""))
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    raw = raw.translate(_ARABIC_MAP).casefold()
    raw = _PUNCT.sub(" ", raw)
    return _WS.sub(" ", raw).strip()
