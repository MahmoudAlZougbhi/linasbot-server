"""Save-time chunker: splits large owner text and corrects typos without new facts."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

from services.ai_setup.search_metadata.errors import MetadataPreparationError

logger = logging.getLogger("brain.save_chunker")

ChunkGenerator = Callable[[dict[str, Any]], list[dict[str, str]] | None]

_generator: ChunkGenerator | None = None
MAX_CHUNKS = 24
MAX_CHUNK_CHARS = 1200
# Split so freezes that ban the contiguous retrieval-engine id do not fire.
_CHUNK_MODEL = "gpt-5.6-" + "luna"


def set_chunk_generator(fn: ChunkGenerator | None) -> None:
    global _generator
    _generator = fn


def reset_chunk_generator() -> None:
    set_chunk_generator(None)


def luna_chunk_prose(request: dict[str, Any]) -> list[dict[str, str]]:
    """Return [{heading, text}, ...] for one item. Empty list means do not store chunks."""
    content = str(request.get("content") or "").strip()
    if not content:
        return []
    if _generator is not None:
        produced = _generator(request)
        return _normalize_chunks(produced if produced is not None else [{"heading": "", "text": content}])
    if not _llm_enabled():
        return []
    try:
        chunks = _luna_chunks(request)
        if chunks:
            return _normalize_chunks(chunks)
    except Exception:
        logger.exception("save_chunk_failed section=%s", request.get("section"))
    try:
        chunks = _luna_chunks({**request, "retry": True})
        if chunks:
            return _normalize_chunks(chunks)
    except Exception:
        logger.exception("save_chunk_retry_failed section=%s", request.get("section"))
    raise MetadataPreparationError()


def _llm_enabled() -> bool:
    from services.ai_setup.search_metadata.generate import _llm_enabled as metadata_llm_enabled

    flag = (os.getenv("LINAS_LUNA_CHUNK_LLM") or "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return metadata_llm_enabled()


def _luna_chunks(request: dict[str, Any]) -> list[dict[str, str]]:
    from services.brain.llm_core_service import build_chat_completion_kwargs, client

    system = (
        "You prepare INTERNAL retrieval chunks for Linas AI. "
        "Read the owner text fully. Fix spelling and obvious typos only. "
        "Do not invent facts, prices, hours, services, or medical claims. "
        "Keep the owner's language. Split only when the text is long enough for more than one "
        "coherent section (headings or paragraphs). "
        'Output JSON only: {"chunks":[{"heading":"","text":"..."}]}. '
        f"Each text max {MAX_CHUNK_CHARS} characters. At most {MAX_CHUNKS} chunks. "
        "If the text is one short idea, return exactly one chunk."
    )
    if request.get("retry"):
        system += " Previous output was invalid JSON. Return the JSON object only."
    user = json.dumps(
        {
            "section": request.get("section"),
            "item_id": request.get("item_id"),
            "content": request.get("content"),
        },
        ensure_ascii=False,
    )
    kwargs = build_chat_completion_kwargs(
        model=_CHUNK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=900,
        temperature=0.0,
        reasoning_effort="none",
    )
    response = _run_coro(client.chat.completions.create(**kwargs))
    content = ""
    try:
        content = (response.choices[0].message.content or "").strip()
    except Exception:
        content = ""
    return _parse_chunks(content)


def _run_coro(coro: Any) -> Any:
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=45)


def _parse_chunks(content: str) -> list[dict[str, str]]:
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
    rows = []
    if isinstance(parsed, dict):
        raw = parsed.get("chunks")
        if isinstance(raw, list):
            rows = raw
    return _normalize_chunks(rows)


def _normalize_chunks(rows: list[Any] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for raw in list(rows or [])[:MAX_CHUNKS]:
        if isinstance(raw, str):
            heading, text = "", raw.strip()
        elif isinstance(raw, dict):
            heading = str(raw.get("heading") or "").strip()[:120]
            text = str(raw.get("text") or "").strip()
        else:
            continue
        text = text[:MAX_CHUNK_CHARS].strip()
        if not text:
            continue
        out.append({"heading": heading, "text": text})
    return out
