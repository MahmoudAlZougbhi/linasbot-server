"""Arabic / Arabizi light normalization for lexical retrieval."""

from __future__ import annotations

import re

_ARABIZI = {
    "3": "ع",
    "7": "ح",
    "5": "خ",
    "2": "أ",
    "8": "غ",
    "6": "ط",
    "9": "ق",
    "sh": "ش",
    "ch": "ش",
    "kh": "خ",
    "gh": "غ",
    "th": "ث",
    "dh": "ذ",
}

_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670]")
_ALEF = re.compile(r"[إأآٱ]")
_TA_MARBUTA = re.compile(r"ة")
_ALEF_MAQSURA = re.compile(r"ى")
_NON_ALNUM = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize_arabic(text: str) -> str:
    body = (text or "").strip().lower()
    if not body:
        return ""
    body = _DIACRITICS.sub("", body)
    body = _ALEF.sub("ا", body)
    body = _TA_MARBUTA.sub("ه", body)
    body = _ALEF_MAQSURA.sub("ي", body)
    # Cheap Arabizi digit-letter swaps for query side only.
    for src, dst in sorted(_ARABIZI.items(), key=lambda kv: -len(kv[0])):
        body = body.replace(src, dst)
    body = _NON_ALNUM.sub(" ", body)
    return " ".join(body.split())
