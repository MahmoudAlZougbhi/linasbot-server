"""OpenAI tool schemas for Owner Copilot V2 (no creative tools)."""

from __future__ import annotations

from typing import Any

from services.owner_copilot_v2.tool_schemas_cm import OWNER_V2_CM_TOOL_SCHEMAS

OWNER_V2_CORE_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "help",
            "description": "Retrieve Linas product capability help for a query.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_account_summary",
            "description": "Read setup stage, CM completeness, integrations, plan, wallet brief.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_profile",
            "description": "Read owner profile (display name, language, address).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_cm",
            "description": (
                "Read AI Setup draft content for internal analysis. Omit section "
                "for inventory overview. With section, returns full bodies (paginated via "
                "items_offset when payload_complete is false). Use freely to gather truth; "
                "user-facing replies stay concise unless the owner asked for a full dump."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "items_offset": {
                        "type": "integer",
                        "description": "Continue a large section from items_next_offset.",
                    },
                    "items_limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_usage",
            "description": "Read usage and credit wallet snapshot.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_subscription",
            "description": "Read subscription/plan entitlements.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_integrations",
            "description": "Read Instagram/Facebook connection and health metadata (read-only).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_meta_health",
            "description": "Evidence-based consolidated IG/FB diagnosis (read-only; no Meta mutations).",
            "parameters": {
                "type": "object",
                "properties": {"channel": {"type": "string", "enum": ["instagram", "facebook", "all"]}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_dashboard_metrics",
            "description": "Read dashboard metrics and setup signals.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_customer_interactions",
            "description": "List recent customer DM/comment interactions for diagnosis.",
            "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_interaction_trace",
            "description": "Load a customer interaction TRACE for diagnosis.",
            "parameters": {"type": "object", "properties": {"trace_id": {"type": "string"}}, "required": ["trace_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_diagnosis_fix",
            "description": "Propose a diagnosis correction for owner approval.",
            "parameters": {
                "type": "object",
                "properties": {"trace_id": {"type": "string"}, "correction": {"type": "object"}},
                "required": ["trace_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_faq_quota",
            "description": (
                "Read Smart Answers / FAQ entitlement: plan enabled flag, used/max/remaining "
                "entry counts, quota_display, and hit metrics (generations_avoided). "
                "Call before proposing a new Smart Answer when quota may be tight."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_smart_answer",
            "description": (
                "Propose a new Smart Answers / FAQ Q&A for owner Approve. "
                "Use when the owner asks to add a ready-made answer for repeated customer questions. "
                "On Approve the pair auto-translates to ar/en/fr/franco and goes Live (same as CM Approve→Live). "
                "Explain savings: matching customer questions skip a full AI generation. "
                "Does not write until the owner Approves or assents (ok / موافق)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                    "language": {
                        "type": "string",
                        "description": "Source language code: ar, en, fr, or franco.",
                    },
                },
                "required": ["question", "answer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": (
                "Update owner profile fields (display_name, preferred_language, gender, form_of_address). "
                "preferred_language is owner chat/app preference only — it does NOT change "
                "customer DM/comment reply language (that is AI Setup → Languages)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "display_name": {"type": "string"},
                    "preferred_language": {"type": "string"},
                    "gender": {"type": "string"},
                    "form_of_address": {"type": "string"},
                },
            },
        },
    },
]

OWNER_V2_TOOL_SCHEMAS: list[dict[str, Any]] = [
    *OWNER_V2_CORE_TOOL_SCHEMAS,
    *OWNER_V2_CM_TOOL_SCHEMAS,
]


def tool_names() -> list[str]:
    return [str(t["function"]["name"]) for t in OWNER_V2_TOOL_SCHEMAS]
