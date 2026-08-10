"""CM-related Owner Copilot V2 tool schemas (split for line limit)."""

from __future__ import annotations

from typing import Any

OWNER_V2_CM_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "inspect_cm_guide",
            "description": "Inspect real CM completeness (filled/weak/missing) and explain a "
            "section: purpose, why it matters, what to fill, what is still "
            "needed. Use before guiding setup. Skip DONE/filled sections unless "
            "the owner asks to change them.",
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
            "description": "Durable fill-missing plan. Prefer action=start when the owner wants "
            "to fill missing CM items. Skips DONE/filled sections, queues "
            "remaining, focuses one section at a time. Actions: "
            "start|status|advance|skip|cancel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["start", "status", "advance", "skip", "cancel"]},
                    "section": {"type": "string", "description": "Optional section id for skip."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_cm_articles",
            "description": "List knowledge or care CM articles (legacy knowledge “files”) with "
            "metadata only (id, title, status, body_chars). Paginated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "enum": ["knowledge", "care"]},
                    "status": {"type": "string"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_cm_article",
            "description": (
                "Read one knowledge/care CM article including full body (chunk via "
                "body_offset/body_limit when body_complete is false). Do not stop at a "
                "partial body when the owner asked for a full read."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "enum": ["knowledge", "care"]},
                    "article_id": {"type": "string"},
                    "body_offset": {"type": "integer"},
                    "body_limit": {"type": "integer"},
                },
                "required": ["section", "article_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_cm_faq",
            "description": "List FAQ / Smart Answer groups in CM (metadata only). Paginated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_cm_faq",
            "description": "Read one FAQ / Smart Answer group with all language variants.",
            "parameters": {
                "type": "object",
                "properties": {"qa_group_id": {"type": "string"}},
                "required": ["qa_group_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ingest_business_dump",
            "description": "Bulk CM setup: distribute a complete business description (and "
            "optional attachment) into Content Management section patches, start "
            "cm_fill_plan, and propose the first section for owner approval "
            "(draft only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Full business description + reply style."},
                    "reply_style": {"type": "string", "description": "How the AI should reply to customers."},
                    "attachment_id": {"type": "string"},
                    "propose_first": {"type": "boolean"},
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
            "description": "Propose a typed CM section patch for owner confirmation (does not "
            "write until approved). Blocked for DONE/filled sections unless "
            "force_edit=true after the owner explicitly asks to change them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "patch": {"type": "object"},
                    "force_edit": {
                        "type": "boolean",
                        "description": "Required true only "
                        "when editing a "
                        "DONE/filled section "
                        "after explicit owner "
                        "request.",
                    },
                },
                "required": ["section", "patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_cm_article_upsert",
            "description": "Propose create/update of one knowledge or care article (CM “file”). "
            "Does not write until the owner confirms via approve_cm_patch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "enum": ["knowledge", "care"]},
                    "article": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "body": {"type": "string"},
                            "status": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "language": {"type": "string"},
                            "audience": {"type": "string"},
                            "category": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                    },
                },
                "required": ["section", "article"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_cm_faq_upsert",
            "description": "Propose create/update of one FAQ group in CM. Does not write until "
            "owner confirms via approve_cm_patch (Approve→Live). For simple new Q&A pairs that "
            "should auto-translate to ar/en/fr/franco, prefer propose_smart_answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "faq": {
                        "type": "object",
                        "properties": {
                            "qa_group_id": {"type": "string"},
                            "variants": {"type": "array"},
                            "status": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "notes": {"type": "string"},
                            "source_language": {"type": "string"},
                            "reviewed": {"type": "boolean"},
                        },
                    }
                },
                "required": ["faq"],
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
            "name": "setup_next_step",
            "description": "Advance or inspect first-run setup inside the same owner chat (same CM draft).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["status", "continue", "skip_section"]},
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
                "properties": {"attachment_id": {"type": "string"}, "notes": {"type": "string"}},
                "required": ["attachment_id"],
            },
        },
    },
]
