"""Reject translator instructions that were copied into the stored answer."""

from __future__ import annotations

_LEAKS = (
    "احتفظ بكل كود",
    "conservez chaque",
    "keep every code",
    "keep every placeholder",
    "exactly as written",
)


def translation_is_clean(source: str, translated: str) -> bool:
    source_lines = [line for line in (source or "").splitlines() if line.strip()]
    output_lines = [line for line in (translated or "").splitlines() if line.strip()]
    if not (translated or "").strip():
        return False
    if len(output_lines) > max(1, len(source_lines)):
        return False
    lowered = translated.casefold()
    return not any(leak.casefold() in lowered for leak in _LEAKS)


def cleanup_candidate(text: str) -> bool:
    lowered = (text or "").casefold()
    return any(leak.casefold() in lowered for leak in _LEAKS)
