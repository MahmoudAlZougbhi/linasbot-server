"""Localize FAQ answers to the visitor's response language."""

from __future__ import annotations

from services.cm.iso639_languages import normalize_language_code


async def localize_faq_answer(
    *,
    answer: str,
    source_language: str | None,
    target_language: str | None,
) -> str:
    """Return answer in target language, translating when needed."""
    text = str(answer or "").strip()
    if not text:
        return ""

    source = normalize_language_code(source_language)
    target = normalize_language_code(target_language)
    if not target or not source or source == target:
        return text

    # Franco and Arabic script share the same customer-facing response language.
    if {source, target} <= {"ar", "franco"}:
        return text

    from services.language_detection_service import language_detection_service

    return await language_detection_service.translate_answer_text(
        text,
        source_language=source,
        target_language=target,
    )
