"""Broad customer message language detection (multilingual replies)."""

from __future__ import annotations

import re

_ISO_LANG_RE = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")


def normalize_language_code(code: str | None) -> str:
    """Normalize to lowercase ISO 639-1 (or product codes ar/en/fr/franco)."""
    raw = str(code or "").strip().lower().replace("_", "-")
    if not raw:
        return ""
    if raw in {"ar", "en", "fr", "franco"}:
        return raw
    base = raw.split("-", 1)[0]
    if base in {"ar", "en", "fr"}:
        return base
    if _ISO_LANG_RE.match(raw):
        return base if len(base) == 2 else raw
    return ""


def detect_broad_customer_language(
    *,
    message: str,
    conversation_id: str,
    accept_language: str | None = None,
) -> str:
    """Detect inbound customer language — product codes plus any ISO language via langdetect."""
    from language_resolver import LanguageResolver

    resolver = LanguageResolver()
    detected = resolver.resolve(
        conversation_id=conversation_id,
        user_text=message or "",
        accept_language=accept_language,
        user_lang_override=None,
    )
    detected = normalize_language_code(detected)
    if detected in {"ar", "en", "fr", "franco"}:
        return detected

    text = (message or "").strip()
    if not text:
        return detected or "en"

    try:
        from langdetect import DetectorFactory, detect_langs

        DetectorFactory.seed = 0
        hits = detect_langs(text)
        if hits:
            top = hits[0]
            if float(top.prob) >= 0.55:
                code = normalize_language_code(str(top.lang))
                if code:
                    return code
    except Exception:
        pass

    return detected or "en"
