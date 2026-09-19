"""OpenAI tool schemas for Sol portal extras (batch approve, comments, dig)."""

from __future__ import annotations

from typing import Any

OWNER_V2_SOL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_pending_cm_proposals",
            "description": "List pending AI Setup proposal cards for this owner. Approving one does not discard siblings.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_cm_batch",
            "description": (
                "Approve selected pending CM proposals after the owner taps Approve all/selected. "
                "Never call with confirmed=true unless confirm_tool / Approve bar fired."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "proposal_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["proposal_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_connected_posts",
            "description": "List connected Facebook/Instagram/TikTok posts the owner can attach to a comment rule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string"},
                    "after": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_comment_rule",
            "description": (
                "Draft a comment/DM rule (COMMENT_ONLY / DM_ONLY / BOTH, static vs AI). "
                "If required fields are missing, ask — do not guess — then propose for Approve."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "action": {"type": "string"},
                    "mode": {"type": "string"},
                    "rule_mode": {"type": "string"},
                    "reply_template": {"type": "string"},
                    "dm_template": {"type": "string"},
                    "ai_instructions": {"type": "string"},
                    "post_id": {"type": "string"},
                    "platform": {"type": "string"},
                    "channel": {"type": "string"},
                    "trigger_type": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "scope": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dig_tenant_cm",
            "description": (
                "Deep tenant health: missing/weak CM, near-duplicate articles/FAQ, "
                "quality_audit, channel flags, recent TRACE samples. Read-only; mutations still need Approve."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_channel_flags",
            "description": "Propose enable/disable of customer channel actions (actions CM). Requires Approve.",
            "parameters": {
                "type": "object",
                "properties": {"patch": {"type": "object"}},
                "required": ["patch"],
            },
        },
    },
]
