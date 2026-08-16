"""Merged AI Basics + Style profile for Tera (storage may still be split)."""

from __future__ import annotations

from typing import Any

from services.customer_reply_v2.manifest import load_fixed_answer_context


def build_ai_profile(fixed_context: dict[str, Any]) -> dict[str, Any]:
    basics = dict(fixed_context.get("ai_basics") or {})
    style = dict(fixed_context.get("style") or {})
    languages = dict(fixed_context.get("languages") or {})
    return {
        "business_identity": basics.get("business_identity")
        or {
            "identity_summary": basics.get("identity_summary"),
            "advanced_instructions": basics.get("advanced_instructions"),
        },
        "assistant_identity": basics.get("assistant_identity") or {"identity_summary": basics.get("identity_summary")},
        "style": style,
        "languages": languages,
        "greeting_rules": basics.get("greeting_rules") or style.get("greeting_rules") or {},
        "welcome_behavior": basics.get("welcome_behavior") or style.get("welcome_behavior") or {},
        "reply_rules": style.get("reply_rules") or basics.get("reply_rules") or {},
    }


def load_tera_ai_context(tenant_id: str) -> dict[str, Any]:
    fixed = load_fixed_answer_context(tenant_id)
    return {
        **fixed,
        "ai_profile": build_ai_profile(fixed),
    }
