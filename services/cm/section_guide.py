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
        "app_path": "AI Setup → AI Basics",
    },
    "languages": {
        "title": "Languages",
        "purpose": (
            "Content/knowledge language organization and default fallback — NOT customer reply language control. "
            "Customer-facing AI replies are multilingual by default (auto-detect, reply in user's language). "
            "Smart Answer translation languages are configured on the Smart Answers / FAQ screen."
        ),
        "why": "Default language and behavior notes still matter for content organization and unknown-language fallback.",
        "what_to_fill": ["supported_languages", "default_language"],
        "useful": (
            "mixed_language_behavior, unknown_language_behavior. "
            "supported_languages does NOT limit customer DM/comment reply languages."
        ),
        "app_path": "AI Setup → Languages",
        "fixed_fields": ["response_language_map", "customer_reply_multilingual"],
        "editable_fields": ["supported_languages", "default_language"],
    },
    "style": {
        "title": "Style & Tone",
        "purpose": "Voice, formality, length, and writing rules.",
        "why": "Keeps every customer reply on-brand.",
        "what_to_fill": ["tone", "formality", "response_length", "style_body"],
        "useful": "do_list / dont_list, example_replies, emoji_level.",
        "app_path": "AI Setup → Style & Tone",
    },
    "dynamic_messages": {
        "title": "Dynamic Messages",
        "purpose": "Greeting and reusable system message templates.",
        "why": "Controls first-touch greetings instead of ad-hoc text.",
        "what_to_fill": ["items[] with name + ar/en/fr text"],
        "useful": "Per-language greeting variants.",
        "app_path": "AI Setup → Dynamic Messages",
    },
    "services": {
        "title": "Services",
        "purpose": "Structured catalog of what the business offers.",
        "why": "Prices, FAQ, care, and answers hang off real service names — not guesses.",
        "what_to_fill": ["items[] with id + labels (ar/en/fr)"],
        "useful": "audience, category, aliases, availability.",
        "app_path": "AI Setup → Services",
    },
    "branches": {
        "title": "Locations",
        "purpose": "Branches / stores / offices the AI can mention.",
        "why": "Customers ask where you are; empty locations force vague or wrong answers.",
        "what_to_fill": ["items[] with id, labels, address/street", "or policy_text if none"],
        "useful": "maps_url, per-branch hours, availability.",
        "app_path": "AI Setup → Locations",
    },
    "opening_hours": {
        "title": "Opening Hours",
        "purpose": "Named Mon–Sun schedules (e.g. Men / Women / Branch).",
        "why": "Customers ask when you are open; weak hours cause wrong open/closed answers.",
        "what_to_fill": ["items[] schedules with open/close or closed per day"],
        "useful": "Multiple named calendars per audience or branch.",
        "app_path": "AI Setup → Opening Hours",
    },
    "prices": {
        "title": "Prices",
        "purpose": "Catalog, price entries, discounts — what the AI may quote.",
        "why": "Without prices the AI must refuse or hand off instead of inventing numbers.",
        "what_to_fill": ["catalog / price_entries / items", "or clear policy_text"],
        "useful": "discount_rules, packages, currency notes.",
        "app_path": "AI Setup → Prices",
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
        "purpose": "Smart Answers — ready-made linked Q&A (ar/en/fr/franco) for repeated customer questions.",
        "why": (
            "Matching questions (same text or meaning) reply from FAQ before a full AI generation — "
            "saves AI credits. Highest-precision answers; production FAQ lives here."
        ),
        "what_to_fill": ["items[] with at least one language question + answer"],
        "useful": "Full four-language variants, tags, review status, plan quota.",
        "app_path": "Smart Answers / FAQ (or AI Setup → FAQ)",
    },
    "handoff": {
        "title": "Human Handoff",
        "purpose": "When and how to send the customer to a human.",
        "why": "Without a real contact destination the AI cannot escalate safely.",
        "what_to_fill": ["contacts[] with destination_type + destination_value"],
        "useful": "matrix rows, policy_text, branch/gender routing.",
        "app_path": "AI Setup → Human Handoff",
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
        "app_path": "AI Setup → Off Days",
    },
    "requests_appointments": {
        "title": "Requests & Appointments",
        "title_ar": "الطلبات والمواعيد",
        "purpose": (
            "Optional customer Orders / Appointment requests / Other capture. "
            "Draft never affects customers until published with module_enabled and enabled_types."
        ),
        "why": "Lets owners collect structured requests without forced wa.me booking handoff.",
        "what_to_fill": [
            "module_enabled",
            "enabled_types (ORDER | APPOINTMENT | OTHER)",
            "fields[] required/optional questions + order/validation",
            "services / products / branches catalogs",
            "messages (acknowledgment, appointment_confirmed, order_ready, completed, cancelled)",
            "notification_language, assignment_defaults, push_enabled, prohibited",
        ],
        "useful": "Leave disabled until ready; empty/unpublished keeps AI capture inactive.",
        "app_path": "AI Setup → Requests & Appointments",
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
