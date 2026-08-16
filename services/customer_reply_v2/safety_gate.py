"""Customer-path Safety Gate — runs before FAQ, Comment AI, Luna, and Tera."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SAFETY_POLICY_VERSION = "customer_safety_v1"
Certainty = Literal["allow", "confirmed_block", "uncertain"]


_BLOCK_REPLIES = {
    "ar": "ما فيني ساعد بهالنوع من المحتوى. إذا في طلب ثاني ضمن خدماتنا، تقدر تكتبلي.",
    "en": "I can't help with that kind of content. If you have another request about our services, I'm here.",
    "fr": "Je ne peux pas aider avec ce type de contenu. Écrivez-nous pour une autre demande liée à nos services.",
    "franco": "Ma fini sa3ed bhal naw3 men el content. Iza 3indak talab tani 3an khidmetna, ktebili.",
}

_BLOCK_REPLIES_PUBLIC = {
    "ar": "ما فيني ساعد بهالنوع من المحتوى.",
    "en": "I can't help with that kind of content.",
    "fr": "Je ne peux pas aider avec ce type de contenu.",
    "franco": "Ma fini sa3ed bhal naw3 men el content.",
}


@dataclass
class CustomerSafetyDecision:
    blocked: bool
    certainty: Certainty
    reasons: list[str] = field(default_factory=list)
    policy_version: str = SAFETY_POLICY_VERSION
    reply: str | None = None
    provider: str | None = None
    incident_id: str | None = None


def _reply_for(*, response_language: str, is_public: bool) -> str:
    table = _BLOCK_REPLIES_PUBLIC if is_public else _BLOCK_REPLIES
    lang = (response_language or "en").strip().lower() or "en"
    if lang == "franco":
        return table["franco"]
    return table.get(lang, table["en"])


async def evaluate_customer_safety(
    *,
    tenant_id: str,
    text: str,
    channel: str,
    user_id: str | None = None,
    response_language: str = "en",
    is_public: bool = False,
    attachment_types: list[str] | None = None,
    image_urls: list[str] | None = None,
) -> CustomerSafetyDecision:
    """Block only on confirmed policy violations. Uncertain results do not stop the turn."""
    from services.customer_reply_v2.channel_metadata import parse_channel
    from services.safety_gateway import safety_gateway

    _platform, surface, parsed_public = parse_channel(channel)
    public = bool(is_public or parsed_public)
    _ = surface
    types = [str(t).strip().lower() for t in (attachment_types or []) if str(t).strip()]
    urls = [str(u).strip() for u in (image_urls or []) if str(u).strip()]

    text_decision = await safety_gateway.check_text(
        tenant_id=tenant_id,
        user_id=user_id,
        text=text or "",
        channel=channel,
    )
    if text_decision.decision == "block":
        return CustomerSafetyDecision(
            blocked=True,
            certainty="confirmed_block",
            reasons=list(text_decision.reasons),
            provider=text_decision.provider,
            incident_id=text_decision.incident_id,
            reply=_reply_for(response_language=response_language, is_public=public),
        )

    media_block = await _check_media_if_present(urls)
    if media_block.get("blocked"):
        return CustomerSafetyDecision(
            blocked=True,
            certainty="confirmed_block",
            reasons=list(media_block.get("reasons") or ["provider_moderation_flagged"]),
            provider=str(media_block.get("provider") or "") or None,
            reply=_reply_for(response_language=response_language, is_public=public),
        )

    uncertain_reasons: list[str] = []
    if media_block.get("uncertain"):
        uncertain_reasons.extend(list(media_block.get("reasons") or ["media_moderation_uncertain"]))
    for kind in types:
        if kind in {"audio", "video", "file"} and not urls:
            uncertain_reasons.append(f"unscanned_attachment:{kind}")

    if uncertain_reasons:
        return CustomerSafetyDecision(
            blocked=False,
            certainty="uncertain",
            reasons=uncertain_reasons,
            provider=str(media_block.get("provider") or "") or None,
        )
    return CustomerSafetyDecision(blocked=False, certainty="allow", reasons=[], provider=text_decision.provider)


async def _check_media_if_present(image_urls: list[str]) -> dict[str, Any]:
    if not image_urls:
        return {"blocked": False, "uncertain": False, "reasons": []}
    try:
        from services import llm_core_service
        from services.providers.base import provider_config

        provider_name = str(provider_config()["moderation"]["provider"])
        client = getattr(llm_core_service, "client", None)
        if provider_name != "openai" or client is None or not hasattr(client, "moderations"):
            return {
                "blocked": False,
                "uncertain": True,
                "reasons": ["media_moderation_unavailable"],
                "provider": provider_name,
            }
        payload: list[dict[str, Any]] = [{"type": "image_url", "image_url": {"url": image_urls[0][:2000]}}]
        resp = await client.moderations.create(model="omni-moderation-latest", input=payload)
        result = resp.results[0]
        if getattr(result, "flagged", False):
            return {
                "blocked": True,
                "uncertain": False,
                "reasons": ["provider_moderation_flagged"],
                "provider": provider_name,
            }
        return {"blocked": False, "uncertain": False, "reasons": [], "provider": provider_name}
    except Exception:
        return {
            "blocked": False,
            "uncertain": True,
            "reasons": ["media_moderation_error"],
        }
