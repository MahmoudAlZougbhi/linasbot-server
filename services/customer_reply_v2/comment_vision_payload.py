"""Keep comment stills out of JSON text so they are not tokenized as huge strings."""

from __future__ import annotations

import base64
import io
import re
from typing import Any

MODEL_MAX_STILLS = 12

_DATA_URL_RE = re.compile(r"^data:(image/[\w.+-]+);base64,(.+)$", re.I | re.DOTALL)
_MAX_EDGE_PX = 1024
_JPEG_QUALITY = 80


def is_data_url(value: str) -> bool:
    return str(value or "").strip().lower().startswith("data:image/")


def strip_data_urls(value: Any) -> Any:
    """Replace data-URL strings with a short marker. Recurse dict/list."""
    if isinstance(value, str):
        if is_data_url(value):
            return "data:image/*;base64,[omitted]"
        return value
    if isinstance(value, dict):
        return {str(key): strip_data_urls(item) for key, item in value.items()}
    if isinstance(value, list):
        return [strip_data_urls(item) for item in value]
    return value


def comment_context_for_text(comment_context: dict[str, Any] | None) -> dict[str, Any]:
    """JSON-safe comment context: caption/status/rules only. No binary stills."""
    ctx = dict(comment_context or {})
    inputs = ctx.pop("image_inputs", None)
    count = len(inputs) if isinstance(inputs, list) else 0
    if count and not ctx.get("image_input_count"):
        ctx["image_input_count"] = count
    ctx["image_inputs_omitted"] = True
    cleaned = strip_data_urls(ctx)
    return cleaned if isinstance(cleaned, dict) else ctx


def compact_data_url(url: str) -> str:
    """Downscale a data URL for vision tiles. Leave https and tiny fixtures alone."""
    raw = str(url or "").strip()
    match = _DATA_URL_RE.match(raw)
    if not match:
        return raw
    try:
        payload = base64.b64decode(match.group(2), validate=False)
    except Exception:
        return raw
    if len(payload) < 2048:
        return raw
    try:
        from PIL import Image
    except Exception:
        return raw
    try:
        opened = Image.open(io.BytesIO(payload))
        image = opened.convert("RGB") if opened.mode != "RGB" else opened
        image.thumbnail((_MAX_EDGE_PX, _MAX_EDGE_PX))
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        encoded = base64.b64encode(out.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return raw


def sample_comment_stills(
    image_inputs: list[dict[str, Any]] | None,
    *,
    max_n: int = MODEL_MAX_STILLS,
) -> list[dict[str, Any]]:
    """Keep first/last stills and even samples so a long reel is not start-only."""
    rows = [row for row in list(image_inputs or []) if isinstance(row, dict)]
    limit = max(0, int(max_n))
    if limit <= 0 or len(rows) <= limit:
        return rows
    if limit == 1:
        return rows[:1]
    step = (len(rows) - 1) / (limit - 1)
    picked: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index in range(limit):
        pos = round(index * step)
        if pos in seen:
            continue
        seen.add(pos)
        picked.append(rows[pos])
    return picked


def vision_image_parts(
    image_inputs: list[dict[str, Any]] | None,
    *,
    max_n: int = MODEL_MAX_STILLS,
) -> list[dict[str, Any]]:
    """Multimodal image_url parts only. Never embed these in the JSON text payload."""
    parts: list[dict[str, Any]] = []
    for row in sample_comment_stills(image_inputs, max_n=max_n):
        url = compact_data_url(str(row.get("url") or "").strip())
        if not url:
            continue
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts
