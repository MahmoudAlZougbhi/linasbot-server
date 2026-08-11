"""Deterministic opt-out phrase detection for Smart Follow-Up cancellation."""

from __future__ import annotations

import re
import unicodedata

# Normalized phrases across supported languages — fail safe when uncertain.
_OPT_OUT_PHRASES = frozenset(
    {
        "stop",
        "stop please",
        "unsubscribe",
        "opt out",
        "optout",
        "do not message me",
        "dont message me",
        "don't message me",
        "no more messages",
        "quit",
        "cancel",
        "end",
        "توقف",
        "وقف",
        "ايقاف",
        "إيقاف",
        "لا تراسلني",
        "لا تراسلنى",
        "الغاء",
        "إلغاء",
        "الغاء الاشتراك",
        "إلغاء الاشتراك",
        "توقف عن المراسلة",
        "arrêt",
        "arreter",
        "arrêter",
        "ne plus menvoyer",
        "ne plus m'envoyer",
        "desabonner",
        "se desabonner",
        "se désabonner",
        "basta",
        "para",
        "parar",
        "no mas",
        "no más",
        "cancelar",
    }
)


def _normalize(text: str) -> str:
    raw = unicodedata.normalize("NFKC", text or "").strip().lower()
    raw = raw.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي")
    raw = re.sub(r"[^\w\s'\u0600-\u06FF-]", " ", raw, flags=re.UNICODE)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def looks_like_opt_out(text: str | None) -> bool:
    """Return True when customer text matches known opt-out phrases.

    Uncertainty policy: short ambiguous stop-like tokens still match; do not
    invent marketing opt-outs. Empty text is not opt-out.
    """
    if not text or not str(text).strip():
        return False
    normalized = _normalize(str(text))
    if not normalized:
        return False
    if normalized in _OPT_OUT_PHRASES:
        return True
    # Whole-message contains exact phrase as standalone token sequence.
    for phrase in _OPT_OUT_PHRASES:
        if len(phrase) >= 4 and phrase in normalized:
            # Require phrase boundary-ish for longer phrases.
            if re.search(rf"(^|\s){re.escape(phrase)}(\s|$)", normalized):
                return True
    # Single-token stop words.
    tokens = set(normalized.split())
    if tokens & {"stop", "unsubscribe", "quit", "توقف", "وقف", "إلغاء", "الغاء", "cancel"}:
        return True
    return False
