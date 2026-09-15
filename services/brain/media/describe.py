"""GPT vision description of stills. Fail closed; never invent clinic facts."""

from __future__ import annotations

import base64
from typing import Any

_BATCH = 4
_MAX_CHARS = 4000
_SYSTEM = (
    "Describe only what is visible in these stills. "
    "Do not invent prices, hours, names, bookings, or clinic facts that are not on screen. "
    "If text is readable, quote it. Keep the description compact."
)


async def describe_stills(
    frames: list[bytes],
    *,
    tenant_id: str,
    kind: str = "image",
) -> str:
    stills = [item for item in frames if item]
    if not stills:
        return ""
    from services.brain.generate.reply import openai_configured

    if not openai_configured():
        return ""
    parts: list[str] = []
    for start in range(0, len(stills), _BATCH):
        chunk = stills[start : start + _BATCH]
        text = await _describe_batch(chunk, tenant_id=tenant_id, kind=kind, offset=start)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()[:_MAX_CHARS]


async def _describe_batch(frames: list[bytes], *, tenant_id: str, kind: str, offset: int) -> str:
    from services.billing.membership.provider_expense import record_pending_provider
    from services.brain.llm_core_service import create_chat_completion
    from services.brain.providers.config import answer_model

    model = answer_model()
    record_pending_provider(
        event_id=f"vision:{tenant_id}:{kind}:{offset}",
        tenant_id=tenant_id,
        category="visual",
        feature="media_analysis",
        provider="openai",
        model=model,
        operation_id=f"{kind}:{offset}",
    )
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Kind={kind}. Stills {offset + 1}-{offset + len(frames)}. Describe visible scenes.",
        }
    ]
    for raw in frames:
        b64 = base64.b64encode(raw).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    try:
        response = await create_chat_completion(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": content},
            ],
            max_tokens=500,
        )
        return str(response.choices[0].message.content or "").strip()
    except Exception:
        return ""
