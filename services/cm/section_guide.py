"""Durable product knowledge for each real CM section (Owner Copilot guide)."""

from __future__ import annotations

from typing import Any

from services.cm.constants import CM_SECTIONS
from services.cm.setup_chat import SECTION_PROMPTS

# Grounded in dashboard CM_SECTION_CARDS + schemas.py — no invented sections.
SECTION_GUIDE: dict[str, dict[str, Any]] = {
    "ai_basics": {
        "title": "AI Basics",
        "purpose": "Business identity, AI name, and embedded style/tone the customer AI speaks as.",
        "why": "Without name + role/purpose, replies feel generic and can invent the wrong business.",
        "what_to_fill": [
            "clinic_name (business display name)",
            "assistant_name",
            "ai_role / business_purpose / short_introduction",
            "style tone/formality/emoji + style_body note (edited in same screen)",
        ],
        "useful": "identity_summary, greeting_behavior, advanced_instructions for edge cases.",
        "app_path": "AI Setup → AI Basics",
    },
    "languages": {
        "title": "Languages",
        "purpose": (
            "Internal content language defaults only. There is no owner Languages tile. "
            "Customer AI auto-detects every supported language and replies in that language. "
            "Franco/Arabizi is understood as Arabic and answered in Arabic script."
        ),
        "why": "Owners do not pick reply languages. FAQ translation targets stay on Smart Q&A.",
        "what_to_fill": [],
        "useful": "Do not tell the owner to enable Arabic/English/French for the customer AI.",
        "app_path": "Not shown in AI Setup. Reply language is global.",
        "fixed_fields": ["response_language_map", "customer_reply_multilingual"],
        "editable_fields": [],
    },
    "style": {
        "title": "Style & Tone",
        "purpose": "Voice, formality, length, and writing rules.",
        "why": "Keeps every customer reply on-brand.",
        "what_to_fill": ["tone", "formality", "response_length", "style_body"],
        "useful": "do_list / dont_list, example_replies, emoji_level.",
        "app_path": "AI Setup → AI Basics → Style",
    },
    "dynamic_messages": {
        "title": "Greetings",
        "purpose": "Greeting rules with title and custom note (edited inside AI Basics).",
        "why": "Owners define how the AI opens conversations.",
        "what_to_fill": [
            "items[] rules: name (title) and notes (custom greeting note)",
            "legacy trigger fields are preserved but optional in mobile UI",
        ],
        "useful": "notes sync to en for runtime; legacy single items migrate to one always rule.",
        "app_path": "AI Setup → AI Basics → Greetings",
    },
    "services": {
        "title": "Services (legacy catalog)",
        "purpose": "Internal legacy service names. The owner Services tile writes the prices catalog.",
        "why": "Kept for published snapshots that still have old service rows.",
        "what_to_fill": [],
        "useful": "Owners add services under AI Setup → Services (prices section).",
        "app_path": "Not a hub tile. Use AI Setup → Services (prices).",
    },
    "branches": {
        "title": "Locations & hours",
        "purpose": "Branches with address, map link, and per-day opening hours / off days.",
        "why": "Customers ask where you are and when you are open; weak data forces vague answers.",
        "what_to_fill": [
            "items[] branch name, maps_url",
            "weekly_schedule per weekday: enabled, open/close or off_day, optional day note",
            "specific_off_rules for holiday closures (optional)",
        ],
        "useful": "timezone, policy_text, branch notes.",
        "app_path": "AI Setup → Locations & hours",
    },
    "opening_hours": {
        "title": "Opening Hours",
        "purpose": "Named Mon–Sun schedules (e.g. Men / Women / Branch).",
        "why": "Customers ask when you are open; weak hours cause wrong open/closed answers.",
        "what_to_fill": ["items[] schedules with open/close or closed per day"],
        "useful": "Multiple named calendars per audience or branch.",
        "app_path": "AI Setup → Locations & hours (hours tab; also used at reply time)",
    },
    "prices": {
        "title": "Services",
        "purpose": "Catalog, price entries, discounts — what the AI may quote.",
        "why": "Without prices the AI must refuse or hand off instead of inventing numbers.",
        "what_to_fill": ["catalog / price_entries / items", "or clear policy_text"],
        "useful": "discount_rules, packages, currency notes.",
        "app_path": "AI Setup → Services",
    },
    "care": {
        "title": "Care / Instructions",
        "purpose": "Prep and aftercare (or operational instructions) tied to services.",
        "why": "Stops unsafe or incomplete advice on how to prepare / recover.",
        "what_to_fill": ["items[] articles with title + body"],
        "useful": "tags, linked_service_ids, audience.",
        "app_path": "AI Setup → Care / Instructions",
    },
    "knowledge": {
        "title": "Knowledge",
        "purpose": "Educational articles for retrieval when FAQ misses.",
        "why": "Gives depth on policies and how the business works without stuffing FAQ.",
        "what_to_fill": ["items[] articles with title + body"],
        "useful": "tags, category, linked services/branches.",
        "app_path": "AI Setup → Knowledge",
    },
    "faq": {
        "title": "FAQ",
        "purpose": "Smart Q&A — ready-made linked Q&A (ar/en/fr/franco) for repeated customer questions.",
        "why": (
            "Matching questions (same text or meaning) reply from FAQ before a full AI generation — "
            "saves AI credits. Highest-precision answers; production FAQ lives here."
        ),
        "what_to_fill": ["items[] with at least one language question + answer"],
        "useful": "Full four-language variants, tags, review status, plan quota.",
        "app_path": "Smart Q&A (or AI Setup → FAQ)",
    },
    "handoff": {
        "title": "Human Handoff contacts",
        "purpose": "Internal contact destinations used after a Requests HUMAN rule transfers to Live Chat.",
        "why": "Owner control for whether to transfer is AI Setup → Requests (HUMAN rule).",
        "what_to_fill": [],
        "useful": "contacts[] remain for published snapshots; do not ask the owner to fill a Handoff tile.",
        "app_path": "AI Setup → Requests (HUMAN type). No separate Handoff tile.",
    },
    "restricted": {
        "title": "Restricted / Unsupported",
        "purpose": "Topics the AI must refuse or never offer.",
        "why": "Prevents selling or discussing things you do not support.",
        "what_to_fill": ["topics[] with labels/keywords", "or notes that nothing is restricted"],
        "useful": "refuse_template, active flags.",
        "app_path": "AI Setup → Restricted",
    },
    "actions": {
        "title": "Channel capability toggles (runtime)",
        "purpose": "Respond_* switches for Meta DMs and comments — edited via Integrations, not a separate UI.",
        "why": "Runtime gates for channel AI without duplicating Integrations controls.",
        "what_to_fill": ["items[] respond_facebook_dm, respond_instagram_dm, respond_*_comments"],
        "useful": "Managed automatically when owners connect channels or toggle DM/comments in Integrations.",
        "app_path": "Integrations (mobile)",
    },
    "comments": {
        "title": "Comments Policy",
        "purpose": (
            "Structured rules for public comments: match keywords → reply on the comment, "
            "reply via private DM, or comment + DM. Optional post_id targeting."
        ),
        "why": "Gives owners precise control over comment behavior beyond the global Actions toggle.",
        "what_to_fill": [
            "rules[] with keywords + action (reply_comment | reply_dm | reply_comment_and_dm)",
            "reply_template for fixed replies / DM text",
            "optional post_id when a rule applies to one post only",
        ],
        "useful": "policy_text for AI when no rule matches; default_action reply_comment.",
        "app_path": "AI Setup → Comments",
    },
    "ai_limits": {
        "title": "Customer AI Limits",
        "purpose": "Per-customer text, photo, and voice caps across connected channels.",
        "why": "Protects credits so one customer cannot burn the owner's AI budget.",
        "what_to_fill": [
            "text_words_per_message",
            "text_replies_per_day/week/month",
            "photos_per_message",
            "image_per_day/week/month",
            "voice_minutes_per_message",
            "voice_minutes_per_day/week/month",
        ],
        "useful": "Save applies immediately to customer replies on WhatsApp, Instagram, and Messenger.",
        "app_path": "Settings → Customer AI Limits (mobile)",
    },
    "off_days": {
        "title": "Off Days",
        "purpose": "Weekly closed days and specific closed dates.",
        "why": "So the AI does not book or promise availability on closed days.",
        "what_to_fill": ["timezone", "rules[] weekly/date/range"],
        "useful": "reason text per rule.",
        "app_path": "AI Setup → Locations & hours",
    },
    "requests_appointments": {
        "title": "Requests & Appointments",
        "title_ar": "الطلبات والمواعيد",
        "purpose": (
            "Optional customer Appointment / Product / Other / Human rules. "
            "Human rules are the owner control for Live Chat / human transfer."
        ),
        "why": "Lets owners collect structured requests and allow human transfer from one Requests screen.",
        "what_to_fill": [
            "rules[] with type (ORDER | APPOINTMENT | OTHER | HUMAN), title (name), and custom note",
        ],
        "useful": "Leave empty until ready; unpublished or no rules keeps AI capture inactive.",
        "app_path": "AI Setup → Requests",
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
