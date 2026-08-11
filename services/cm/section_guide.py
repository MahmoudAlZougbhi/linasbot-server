"""Durable product knowledge for each real CM section (Owner Copilot guide)."""

from __future__ import annotations

from typing import Any

from services.cm.constants import CM_SECTIONS
from services.cm.setup_chat import SECTION_PROMPTS

# Grounded in dashboard CM_SECTION_CARDS + schemas.py — no invented sections.
SECTION_GUIDE: dict[str, dict[str, Any]] = {
    "ai_basics": {
        "title": "AI Basics",
        "purpose": "Business identity and persona the customer AI speaks as.",
        "why": "Without name + role/purpose, replies feel generic and can invent the wrong business.",
        "what_to_fill": [
            "clinic_name (business display name)",
            "assistant_name",
            "ai_role / business_purpose / short_introduction",
        ],
        "useful": "identity_summary, greeting_behavior, advanced_instructions for edge cases.",
        "app_path": "Content Management → AI Basics",
    },
    "languages": {
        "title": "Languages",
        "purpose": (
            "System-standard customer reply language for DMs and comments "
            "(supported languages + Franco → Arabic map + default). "
            "App Settings language is UI-only and does not change customer replies."
        ),
        "why": "Wrong language policy makes the AI reply in the wrong language.",
        "what_to_fill": ["supported_languages", "default_language", "response_language_map"],
        "useful": "mixed_language_behavior, unknown_language_behavior.",
        "app_path": "Content Management → Languages",
    },
    "style": {
        "title": "Style & Tone",
        "purpose": "Voice, formality, length, and writing rules.",
        "why": "Keeps every customer reply on-brand.",
        "what_to_fill": ["tone", "formality", "response_length", "style_body"],
        "useful": "do_list / dont_list, example_replies, emoji_level.",
        "app_path": "Content Management → Style & Tone",
    },
    "dynamic_messages": {
        "title": "Dynamic Messages",
        "purpose": "Greeting and reusable system message templates.",
        "why": "Controls first-touch greetings instead of ad-hoc text.",
        "what_to_fill": ["items[] with name + ar/en/fr text"],
        "useful": "Per-language greeting variants.",
        "app_path": "Content Management → Dynamic Messages",
    },
    "services": {
        "title": "Services",
        "purpose": "Structured catalog of what the business offers.",
        "why": "Prices, FAQ, care, and answers hang off real service names — not guesses.",
        "what_to_fill": ["items[] with id + labels (ar/en/fr)"],
        "useful": "audience, category, aliases, availability.",
        "app_path": "Content Management → Services",
    },
    "branches": {
        "title": "Locations",
        "purpose": "Branches / stores / offices the AI can mention.",
        "why": "Customers ask where you are; empty locations force vague or wrong answers.",
        "what_to_fill": ["items[] with id, labels, address/street", "or policy_text if none"],
        "useful": "maps_url, per-branch hours, availability.",
        "app_path": "Content Management → Locations",
    },
    "opening_hours": {
        "title": "Opening Hours",
        "purpose": "Named Mon–Sun schedules (e.g. Men / Women / Branch).",
        "why": "Customers ask when you are open; weak hours cause wrong open/closed answers.",
        "what_to_fill": ["items[] schedules with open/close or closed per day"],
        "useful": "Multiple named calendars per audience or branch.",
        "app_path": "Content Management → Opening Hours",
    },
    "prices": {
        "title": "Prices",
        "purpose": "Catalog, price entries, discounts — what the AI may quote.",
        "why": "Without prices the AI must refuse or hand off instead of inventing numbers.",
        "what_to_fill": ["catalog / price_entries / items", "or clear policy_text"],
        "useful": "discount_rules, packages, currency notes.",
        "app_path": "Content Management → Prices",
    },
    "care": {
        "title": "Care / Instructions",
        "purpose": "Prep and aftercare (or operational instructions) tied to services.",
        "why": "Stops unsafe or incomplete advice on how to prepare / recover.",
        "what_to_fill": ["items[] articles with title + body"],
        "useful": "tags, linked_service_ids, audience.",
        "app_path": "Content Management → Care / Instructions",
    },
    "knowledge": {
        "title": "Knowledge",
        "purpose": "Educational articles for retrieval when FAQ misses.",
        "why": "Gives depth on policies and how the business works without stuffing FAQ.",
        "what_to_fill": ["items[] articles with title + body"],
        "useful": "tags, category, linked services/branches.",
        "app_path": "Content Management → Knowledge",
    },
    "faq": {
        "title": "FAQ",
        "purpose": "Smart Answers — ready-made linked Q&A (ar/en/fr/franco) for repeated customer questions.",
        "why": (
            "Matching questions (same text or meaning) reply from FAQ before a full AI generation — "
            "saves AI credits. Highest-precision answers; production FAQ lives here."
        ),
        "what_to_fill": ["items[] with at least one language question + answer"],
        "useful": "Full four-language variants, tags, review status, plan quota.",
        "app_path": "Smart Answers / FAQ (or Content Management → FAQ)",
    },
    "handoff": {
        "title": "Human Handoff",
        "purpose": "When and how to send the customer to a human.",
        "why": "Without a real contact destination the AI cannot escalate safely.",
        "what_to_fill": ["contacts[] with destination_type + destination_value"],
        "useful": "matrix rows, policy_text, branch/gender routing.",
        "app_path": "Content Management → Human Handoff",
    },
    "restricted": {
        "title": "Restricted / Unsupported",
        "purpose": "Topics the AI must refuse or never offer.",
        "why": "Prevents selling or discussing things you do not support.",
        "what_to_fill": ["topics[] with labels/keywords", "or notes that nothing is restricted"],
        "useful": "refuse_template, active flags.",
        "app_path": "Content Management → Restricted",
    },
    "actions": {
        "title": "Actions / Capabilities",
        "purpose": "What the AI is allowed to do (FB/IG DM, comments, handoff, photo).",
        "why": "Turns capabilities on/off without code changes.",
        "what_to_fill": ["items[] capability toggles (enabled true/false)"],
        "useful": "Keep photo_analysis off unless you want image analysis.",
        "app_path": "Content Management → Actions",
    },
    "comments": {
        "title": "Comments Policy",
        "purpose": (
            "Structured rules for public comments: match keywords → reply on the comment, "
            "reply via private DM, or ignore. Optional post_id targeting."
        ),
        "why": "Gives owners precise control over comment behavior beyond the global Actions toggle.",
        "what_to_fill": [
            "rules[] with keywords + action (reply_comment | reply_dm | ignore)",
            "reply_template for fixed replies / DM text",
            "optional post_id when a rule applies to one post only",
        ],
        "useful": "policy_text for AI when no rule matches; default_action reply_comment|ignore.",
        "app_path": "Content Management → Comments",
    },
    "ai_limits": {
        "title": "AI Limits",
        "purpose": "Per-customer image/context usage caps and voice/image switches.",
        "why": "Protects cost and abuse once Live.",
        "what_to_fill": ["image_per_day/week", "context_lines_per_day/week", "enforce_* flags"],
        "useful": "voice_processing_enabled, image_analysis_enabled.",
        "app_path": "Content Management → AI Limits",
    },
    "off_days": {
        "title": "Off Days",
        "purpose": "Weekly closed days and specific closed dates.",
        "why": "So the AI does not book or promise availability on closed days.",
        "what_to_fill": ["timezone", "rules[] weekly/date/range"],
        "useful": "reason text per rule.",
        "app_path": "Content Management → Off Days",
    },
}


def guide_for_section(section: str) -> dict[str, Any] | None:
    name = (section or "").strip().replace("-", "_")
    if name not in CM_SECTIONS:
        return None
    base = dict(SECTION_GUIDE.get(name) or {})
    base["section"] = name
    base["interview_prompt"] = SECTION_PROMPTS.get(name, "")
    base["quality_checklist"] = [
        "critique / what’s wrong",
        "duplicates",
        "unclear / confusing",
        "improvements (halwse)",
        "suspicious / placeholder",
    ]
    return base


def list_section_guides() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for section in CM_SECTIONS:
        g = guide_for_section(section)
        if g:
            out.append(g)
    return out
