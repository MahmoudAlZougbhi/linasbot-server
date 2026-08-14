"""Hardcoded in-app welcome pool. Not LLM-generated and not setup-status copy."""

from __future__ import annotations

import random
import threading
from typing import Literal

from services.welcome_pool.ar import WELCOME_AR
from services.welcome_pool.en import WELCOME_EN
from services.welcome_pool.fr import WELCOME_FR

Lang = Literal["ar", "en", "fr"]

POOLS: dict[str, tuple[str, ...]] = {
    "en": WELCOME_EN,
    "ar": WELCOME_AR,
    "fr": WELCOME_FR,
}

MIN_POOL_SIZE = 50

# Phrases from the old stage-status greeting that must never reappear.
BANNED_SNIPPETS: tuple[str, ...] = (
    "core looks configured",
    "everything core",
    "ai setup",
    "system copilot",
    "ask me about usage",
    "integrations anytime",
    "connect meta",
    "configuration ia",
    "الإعداد الأساسي يبدو مكتملاً",
    "تعديلات إعداد الذكاء",
    "l’essentiel semble configuré",
    "ajustements configuration ia",
)

_lock = threading.Lock()
_last_index: dict[str, int] = {}


def lines_for(language: str) -> tuple[str, ...]:
    if language not in POOLS:
        raise KeyError(f"unsupported welcome language: {language}")
    pool = POOLS[language]
    if not pool:
        raise RuntimeError(f"empty welcome pool for {language}")
    return pool


def pick_welcome_line(
    *,
    language: str,
    user_key: str,
    rng: random.Random | None = None,
) -> str:
    pool = lines_for(language)
    chooser = rng or random
    with _lock:
        last = _last_index.get(user_key)
        idx = chooser.randrange(len(pool))
        if last is not None and len(pool) > 1 and idx == last:
            idx = (idx + 1) % len(pool)
        _last_index[user_key] = idx
        return pool[idx]


def format_welcome(template: str, *, hi: str) -> str:
    return template.format(hi=hi)


def pick_welcome(
    *,
    language: str,
    user_key: str,
    hi: str,
    rng: random.Random | None = None,
) -> str:
    return format_welcome(
        pick_welcome_line(language=language, user_key=user_key, rng=rng),
        hi=hi,
    )


def reset_last_picks() -> None:
    with _lock:
        _last_index.clear()
