"""OpenAI tool schemas for Owner Copilot V2 (no creative tools)."""

from __future__ import annotations

from typing import Any

# Structured tool calling — Sol plans these; regex is not the primary router.
OWNER_V2_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "help",
            "description": "Retrieve Linas product capability help for a query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
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
            "description": "Read Content Management draft/live snapshot for a section or overview.",
            "parameters": {
                "type": "object",
                "properties": {"section": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_cm_guide",
            "description": (
                "Inspect real CM completeness (filled/weak/missing) and explain a section: "
                "purpose, why it matters, what to fill, what is still needed. "
                "Use before guiding setup. Skip DONE/filled sections unless the owner asks to change them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": "Optional CM section id (e.g. ai_basics, faq). Omit for full overview.",
                    },
                    "include_guides": {
                        "type": "boolean",
                        "description": "Include compact per-section purpose index (default true on overview).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cm_fill_plan",
            "description": (
                "Durable fill-missing plan. Prefer action=start when the owner wants to fill missing CM items. "
                "Skips DONE/filled sections, queues remaining, focuses one section at a time. "
                "Actions: start|status|advance|skip|cancel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["start", "status", "advance", "skip", "cancel"],
                    },
                    "section": {
                        "type": "string",
                        "description": "Optional section id for skip.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_cm",
            "description": "Validate current CM draft.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_cm_patch",
            "description": (
                "Propose a typed CM section patch for owner confirmation (does not write until approved). "
                "Blocked for DONE/filled sections unless force_edit=true after the owner explicitly asks to change them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "patch": {"type": "object"},
                    "force_edit": {
                        "type": "boolean",
                        "description": "Required true only when editing a DONE/filled section after explicit owner request.",
                    },
                },
                "required": ["section", "patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "publish_cm",
            "description": "Request publish of validated CM (high-impact; requires confirmation).",
            "parameters": {"type": "object", "properties": {}},
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
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_interaction_trace",
            "description": "Load a customer interaction TRACE for diagnosis.",
            "parameters": {
                "type": "object",
                "properties": {"trace_id": {"type": "string"}},
                "required": ["trace_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_diagnosis_fix",
            "description": "Propose a diagnosis correction for owner approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trace_id": {"type": "string"},
                    "correction": {"type": "object"},
                },
                "required": ["trace_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_faq_quota",
            "description": "Read Smart Answers / FAQ quota.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_smart_answer",
            "description": "Propose a Smart Answer FAQ entry for approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                    "language": {"type": "string"},
                },
                "required": ["question", "answer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": "Update owner profile fields (display_name, preferred_language, gender, form_of_address).",
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
    {
        "type": "function",
        "function": {
            "name": "setup_next_step",
            "description": "Advance or inspect first-run setup inside the same owner chat (same CM draft).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "continue", "skip_section"],
                    },
                    "section": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_price_list",
            "description": "Analyze an uploaded price-list attachment and return structured extraction (no CM write).",
            "parameters": {
                "type": "object",
                "properties": {
                    "attachment_id": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["attachment_id"],
            },
        },
    },
]


def tool_names() -> list[str]:
    return [str(t["function"]["name"]) for t in OWNER_V2_TOOL_SCHEMAS]
