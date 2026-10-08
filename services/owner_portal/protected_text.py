"""Keep names, codes, and labels intact across translation."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+|\d{2,}")
Translate = Callable[[str, int], Awaitable[str]]


def mask_tokens(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def repl(match: re.Match[str]) -> str:
        tokens.append(match.group(0))
        return f"⟦T{len(tokens)}⟧"

    return _TOKEN.sub(repl, text or ""), tokens


def restore_tokens(text: str, tokens: list[str]) -> str:
    restored = text or ""
    for index, token in enumerate(tokens, start=1):
        restored = restored.replace(f"⟦T{index}⟧", token)
    return restored


def _placeholders_kept(text: str, tokens: list[str]) -> bool:
    return all(f"⟦T{index}⟧" in (text or "") for index in range(1, len(tokens) + 1))


def _tokens_kept(text: str, tokens: list[str]) -> bool:
    return all(token in (text or "") for token in tokens)


async def translate_kept(text: str, *, target: str, translate: Translate) -> tuple[str, int]:
    """Translate with placeholders. Retry once, then put any missing tokens back."""
    original = (text or "").strip()
    masked, tokens = mask_tokens(original)
    if not tokens:
        rendered = (await translate(original, 1)).strip() or original
        return rendered, 1
    last = ""
    attempts = 0
    for attempt in (1, 2):
        attempts = attempt
        last = (await translate(masked, attempt)).strip()
        if _placeholders_kept(last, tokens):
            return restore_tokens(last, tokens).strip(), attempts
        if _tokens_kept(last, tokens) and "⟦T" not in last:
            return last, attempts
    missing = [token for token in tokens if token not in restore_tokens(last, tokens)]
    logger.warning("translation dropped tokens language=%s missing=%s", target, ",".join(missing))
    restored = restore_tokens(last, tokens).strip()
    for token in tokens:
        if token not in restored:
            restored = f"{restored} {token}".strip()
    return restored or original, attempts
