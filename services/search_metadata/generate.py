"""Generate English-only search metadata for one changed item."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from services.search_metadata.english import english_only_or_empty
from services.search_metadata.errors import MetadataPreparationError
from services.search_metadata.limits import (
    AI_SEARCH_DESCRIPTION_MAX,
    AI_SEARCH_KEYWORD_MAX,
    AI_SEARCH_KEYWORDS_MAX,
    AI_SEARCH_TITLE_MAX,
)

logger = logging.getLogger("search_metadata.generate")

MetadataGenerator = Callable[[dict[str, Any]], "SearchMetadata | None"]

_generator: MetadataGenerator | None = None
_LAST_GENERATE: dict[str, Any] = {"llm_calls": 0, "retries": 0, "failed": False, "saved_empty": False}

_WEAK_DESCRIPTIONS = frozenset(
    {
        "aaa",
        "good product",
        "nice product",
        "product",
        "test",
        "n/a",
        "na",
        "none",
        "ok",
        "good",
        "123",
    }
)


@dataclass
class SearchMetadata:
    title: str = ""
    description: str = ""
    keywords: list[str] = field(default_factory=list)


def set_metadata_generator(fn: MetadataGenerator | None) -> None:
    global _generator
    _generator = fn


def reset_metadata_generator() -> None:
    set_metadata_generator(None)
    _LAST_GENERATE.update({"llm_calls": 0, "retries": 0, "failed": False, "saved_empty": False})


def last_generate_stats() -> dict[str, Any]:
    return dict(_LAST_GENERATE)


def is_weak_owner_description(text: str) -> bool:
    raw = " ".join(str(text or "").split())
    if not raw:
        return True
    lowered = raw.lower()
    if lowered in _WEAK_DESCRIPTIONS:
        return True
    if re.fullmatch(r"[\d\W_]+", raw):
        return True
    letters = sum(1 for c in raw if c.isalpha())
    return letters < 6


def clamp_metadata(meta: SearchMetadata, *, include_keywords: bool) -> SearchMetadata:
    title = english_only_or_empty(meta.title, require_english_language=True)[:AI_SEARCH_TITLE_MAX]
    description = english_only_or_empty(meta.description, require_english_language=True)[:AI_SEARCH_DESCRIPTION_MAX]
    keywords: list[str] = []
    if include_keywords:
        seen: set[str] = set()
        for raw in list(meta.keywords or [])[:AI_SEARCH_KEYWORDS_MAX]:
            word = english_only_or_empty(str(raw), require_english_language=False)[:AI_SEARCH_KEYWORD_MAX]
            key = word.lower()
            if not word or key in seen:
                continue
            seen.add(key)
            keywords.append(word)
    return SearchMetadata(title=title, description=description, keywords=keywords)


def generate_search_metadata(request: dict[str, Any]) -> SearchMetadata:
    """Create compact English metadata from one item's grounded content.

    ``request`` must include original_title + content. Does not read other tenant items.
    Empty, non-English, language-clamped, or ungrounded results raise
    ``MetadataPreparationError`` after the allowed retry. Callers must not Save/live.
    """
    from services.search_metadata.validate import require_ready_metadata

    include_keywords = bool(request.get("include_keywords"))
    content = str(request.get("content") or "")
    original_title = str(request.get("original_title") or "")
    _LAST_GENERATE.update({"llm_calls": 0, "retries": 0, "failed": False, "saved_empty": False})

    def _accept(raw: SearchMetadata) -> SearchMetadata:
        clamped = clamp_metadata(raw, include_keywords=include_keywords)
        try:
            return require_ready_metadata(
                clamped,
                include_keywords=include_keywords,
                content=content,
                original_title=original_title,
            )
        except MetadataPreparationError:
            _LAST_GENERATE["saved_empty"] = not clamped.title and not clamped.description
            _LAST_GENERATE["failed"] = True
            raise

    if _generator is not None:
        produced = _generator(request)
        meta = produced if produced is not None else SearchMetadata()
        return _accept(meta)
    if not _llm_enabled():
        _LAST_GENERATE.update({"failed": True, "saved_empty": True})
        raise MetadataPreparationError()
    produced = SearchMetadata()
    try:
        produced = _generate_with_luna(request)
        _LAST_GENERATE["llm_calls"] = 1
    except Exception:
        logger.exception("search_metadata_luna_failed kind=%s", request.get("kind"))
        _LAST_GENERATE["failed"] = True
    try:
        return _accept(produced)
    except MetadataPreparationError:
        retry_req = dict(request)
        retry_req["english_retry"] = True
        try:
            produced = _generate_with_luna(retry_req)
            _LAST_GENERATE["llm_calls"] = int(_LAST_GENERATE["llm_calls"] or 0) + 1
            _LAST_GENERATE["retries"] = 1
            _LAST_GENERATE["failed"] = False
            return _accept(produced)
        except MetadataPreparationError:
            raise
        except Exception:
            logger.exception("search_metadata_luna_english_retry_failed kind=%s", request.get("kind"))
            _LAST_GENERATE.update({"failed": True, "saved_empty": True})
            raise MetadataPreparationError() from None


def _llm_enabled() -> bool:
    flag = (os.getenv("LINAS_SEARCH_METADATA_LLM") or "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    env = (os.getenv("ENVIRONMENT") or "").strip().lower()
    if env in {"test", "ci"} and flag not in {"1", "true", "yes", "on"}:
        return False
    return bool((os.getenv("OPENAI_API_KEY") or "").strip())


def _generate_with_luna(request: dict[str, Any]) -> SearchMetadata:
    from services.llm_core_service import build_chat_completion_kwargs, client
    from services.model_policy import MODEL_CUSTOMER_LUNA

    include_keywords = bool(request.get("include_keywords"))
    weak = bool(request.get("weak_description"))
    system = (
        "You write INTERNAL English-only search metadata for Linas AI. "
        "Read the provided item content fully. Do not invent facts, prices, medical claims, "
        "categories, or use-cases that are not explicitly present. "
        "Output JSON only: "
        '{"ai_search_title":"...","ai_search_description":"..."'
        + (',"ai_search_keywords":["..."]' if include_keywords else "")
        + "}. "
        f"ai_search_title max {AI_SEARCH_TITLE_MAX} characters, specific, English. "
        f"ai_search_description max {AI_SEARCH_DESCRIPTION_MAX} characters, one short sentence "
        "or two very short sentences explaining what the item contains and when it is useful. "
        "Never copy a non-English script into these fields. "
        "English only — not French, Spanish, German, Italian, or any other language. "
        "These fields are search hints, not business facts."
    )
    if request.get("english_retry"):
        system += (
            " Previous output was not English. Rewrite the same grounded facts in English only. "
            "Do not invent new facts."
        )
    if weak:
        system += (
            " The owner description is weak or uninformative. Do not infer product type, "
            "category, or use. Title may transliterate the real name only."
        )
    user = json.dumps(
        {
            "kind": request.get("kind"),
            "section": request.get("section"),
            "original_title": request.get("original_title"),
            "content": request.get("content"),
            "include_keywords": include_keywords,
            "weak_description": weak,
        },
        ensure_ascii=False,
    )
    kwargs = build_chat_completion_kwargs(
        model=MODEL_CUSTOMER_LUNA,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=220,
        temperature=0.0,
        reasoning_effort="none",
    )
    response = _run_coro(client.chat.completions.create(**kwargs))
    content = ""
    try:
        content = (response.choices[0].message.content or "").strip()
    except Exception:
        content = ""
    return _parse_metadata(content, include_keywords=include_keywords)


def _run_coro(coro: Any) -> Any:
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=45)


def _parse_metadata(content: str, *, include_keywords: bool) -> SearchMetadata:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    parsed: Any = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                parsed = None
    if not isinstance(parsed, dict):
        return SearchMetadata()
    keywords = parsed.get("ai_search_keywords") or parsed.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    return SearchMetadata(
        title=str(parsed.get("ai_search_title") or parsed.get("title") or ""),
        description=str(parsed.get("ai_search_description") or parsed.get("description") or ""),
        keywords=[str(k) for k in keywords] if include_keywords else [],
    )
