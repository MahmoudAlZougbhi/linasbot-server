"""Search/FAQ normalization. Does not strip negation, quantities, or currency."""

from __future__ import annotations

import re
import unicodedata

_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize_search_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
    text = text.casefold()
    text = _PUNCT.sub(" ", text)
    return _SPACE.sub(" ", text).strip()
