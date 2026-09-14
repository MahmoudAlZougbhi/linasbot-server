"""Creative product is cancelled for System Copilot V2 — dormant paths only."""

from __future__ import annotations

from typing import Any

CANCELLED_CREATIVE_TOOLS = frozenset(
    {
        "create_creative_draft",
        "schedule_creative_draft",
        "read_scheduled_posts",
    }
)

CREATIVE_KEYWORDS = (
    "create post",
    "create a post",
    "make a post",
    "make post",
    "create a story",
    "create story",
    "reel",
    "reels",
    "caption",
    "creative studio",
    "schedule post",
    "generate image",
    "generate video",
    "بوست",
    "منشور",
    "ستوري",
    "ريلز",
)


def looks_like_creative_request(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in CREATIVE_KEYWORDS)


def creative_refusal_message(*, language: str = "en") -> str:
    if language == "ar":
        return (
            "حالياً Linas AI يركّز على أتمتة رسائل وتعليقات إنستغرام وفيسبوك، "
            "وليس على إنشاء منشورات أو صور أو فيديوهات. "
            "أقدر أساعدك بإعداد معرفة نشاطك، التكاملات، التشخيص، والاستخدام."
        )
    if language == "fr":
        return (
            "Linas AI se concentre actuellement sur l’automatisation des messages et commentaires "
            "Instagram/Facebook, pas sur la création de posts, images ou vidéos. "
            "Je peux vous aider pour la configuration, les intégrations, le diagnostic et l’usage."
        )
    return (
        "Linas AI currently focuses on automating Instagram and Facebook DMs and comments — "
        "not creating posts, stories, images, or videos. "
        "I can help with AI Setup, integrations, diagnosis, and usage."
    )


def creative_tool_blocked_result(name: str, *, language: str = "en") -> dict[str, Any]:
    return {
        "ok": False,
        "name": name,
        "data": {
            "status": "cancelled",
            "reason": "creative_product_cancelled",
            "message": creative_refusal_message(language=language),
        },
        "error": "creative_product_cancelled",
        "requires_confirmation": False,
    }
