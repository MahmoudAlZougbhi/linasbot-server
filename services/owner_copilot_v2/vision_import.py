"""Vision / OCR price-list extraction contract for Owner Copilot V2.

Uses provider multimodal when available; otherwise a dedicated extraction path.
Never invents high-confidence prices from filenames alone.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from typing import Any

from services.owner_ai_tools_base import ToolResult


def multimodal_supported() -> bool:
    """Whether the configured owner/vision path accepts image input.

    Override with LINAS_OWNER_VISION_MODE=multimodal|ocr|unavailable.
    """
    mode = (os.getenv("LINAS_OWNER_VISION_MODE") or "multimodal").strip().lower()
    return mode in {"multimodal", "auto", "1", "true"}


async def _extract_via_vision(
    *,
    model: str,
    mime: str,
    content: bytes,
    notes: str,
) -> dict[str, Any]:
    from services.llm_core_service import build_chat_completion_kwargs, client

    b64 = base64.b64encode(content).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Extract a structured price list from the image/document. "
                "Return JSON only with keys: document_type, currency_guess, items "
                "(array of {name, category, price, currency, branch, notes, confidence}), "
                "ambiguities (array of strings), summary. "
                "Use confidence 0-1. Never invent unreadable prices; mark low confidence."
            ),
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": notes or "Extract services and prices."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]
    kwargs = build_chat_completion_kwargs(
        model=model,
        messages=messages,
        max_tokens=2000,
        temperature=0.2,
        reasoning_effort="high",
    )
    # messages may include multimodal content — rebuild without type restriction
    kwargs["messages"] = messages
    response = await client.chat.completions.create(**kwargs)
    raw = (response.choices[0].message.content or "").strip()
    try:
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].strip()
        loaded = json.loads(raw)
        parsed: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
    except Exception:
        parsed = {
            "document_type": "unknown",
            "currency_guess": None,
            "items": [],
            "ambiguities": ["model_returned_non_json"],
            "summary": "Could not parse structured extraction; please review manually.",
            "raw_preview": raw[:500],
        }
    parsed["provider_model"] = model
    parsed["vision_path"] = "multimodal"
    parsed["image_received"] = True
    return parsed


def _fixture_or_unavailable(*, attachment_id: str, reason: str) -> dict[str, Any]:
    return {
        "attachment_id": attachment_id,
        "extraction_id": f"ext_{uuid.uuid4().hex[:12]}",
        "document_type": "price_list",
        "currency_guess": None,
        "items": [],
        "ambiguities": [reason],
        "summary": (
            "Vision extraction is not available in this environment. "
            "The attachment was stored privately; no CM changes were made."
        ),
        "vision_path": "unavailable",
        "image_received": False,
        "provider_model": None,
    }


async def tool_extract_price_list(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    attachment_id: str,
    notes: str = "",
) -> ToolResult:
    del role, user_id
    from services.owner_copilot_v2.attachments import load_attachment_bytes, load_attachment_meta
    from services.owner_copilot_v2.flags import owner_model_name

    meta = load_attachment_meta(tenant_id=tenant_id, attachment_id=attachment_id)
    if not meta:
        return ToolResult(
            ok=False,
            name="extract_price_list",
            data={},
            error="attachment_not_found_or_forbidden",
        )
    content = load_attachment_bytes(tenant_id=tenant_id, attachment_id=attachment_id)
    if not content:
        return ToolResult(ok=False, name="extract_price_list", data={}, error="attachment_bytes_missing")

    mime = str(meta.get("mime") or "image/jpeg")
    model = owner_model_name()

    # Allow offline/CI fixtures without calling the provider
    if (os.getenv("LINAS_OWNER_VISION_FIXTURE") or "").strip():
        fixture_path = (os.getenv("LINAS_OWNER_VISION_FIXTURE") or "").strip()
        try:
            data = json.loads(open(fixture_path, encoding="utf-8").read())
            data.setdefault("attachment_id", attachment_id)
            data.setdefault("extraction_id", f"ext_{uuid.uuid4().hex[:12]}")
            data["vision_path"] = "fixture"
            data["image_received"] = True
            return ToolResult(ok=True, name="extract_price_list", data=data)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, name="extract_price_list", data={}, error=f"fixture_error:{exc}")

    if not multimodal_supported():
        data = _fixture_or_unavailable(attachment_id=attachment_id, reason="vision_mode_unavailable")
        return ToolResult(ok=True, name="extract_price_list", data=data)

    try:
        parsed = await _extract_via_vision(model=model, mime=mime, content=content, notes=notes)
    except Exception as exc:  # noqa: BLE001
        # Honest failure — do not fake OCR from filename
        return ToolResult(
            ok=False,
            name="extract_price_list",
            data={
                "attachment_id": attachment_id,
                "image_received": False,
                "vision_path": "error",
                "error": type(exc).__name__,
            },
            error=f"vision_unavailable:{type(exc).__name__}",
        )

    parsed["attachment_id"] = attachment_id
    parsed.setdefault("extraction_id", f"ext_{uuid.uuid4().hex[:12]}")
    # Normalize items confidence
    raw_items = parsed.get("items")
    items: list[Any] = raw_items if isinstance(raw_items, list) else []
    for item in items:
        if isinstance(item, dict) and "confidence" not in item:
            item["confidence"] = 0.5
    parsed["items"] = items
    parsed["cm_mutated"] = False
    return ToolResult(ok=True, name="extract_price_list", data=parsed)
