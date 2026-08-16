"""OpenAI function schemas for Retrieval Luna tools."""

from __future__ import annotations

from typing import Any

RETRIEVAL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_published_cm_sections",
            "description": "List Published CM sections (manifest). AI Basics/Style are fixed Answer context and not selectable.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_operational_titles",
            "description": "Page all operational titles (services, knowledge, hours, locations, request rules, comment AI-guidance). Does not include AI Basics, Style, or the product catalog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_published_cm_items",
            "description": "List item-index metadata for selected selectable Published sections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["section_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_published_cm_items",
            "description": "Read full allowed contents for exact Published item IDs from the current revision. Oversized files return file_too_large instead of silent truncation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["item_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_additional_published_cm_items",
            "description": "Request one additional retrieval round of sections/items. Server refuses after round 2.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section_ids": {"type": "array", "items": {"type": "string"}},
                    "item_ids": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_safe_customer_profile",
            "description": "Read safe persistent customer facts for this conversation (no cross-tenant data).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dm_context_window",
            "description": "Read the rolling conversation window already loaded by the server.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_comment_post_context",
            "description": "Read comment/post media context for comment events (not DM history).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_product_by_title",
            "description": "Search tenant products by title (exact/normalized first). On miss, returns a titles-only page in this same retrieval loop. Never dumps price, images, or the full catalog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_product_titles",
            "description": "Page active product titles only (id, title, status) for the current tenant. No prices, notes, or media.",
            "parameters": {
                "type": "object",
                "properties": {
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": "Read details for one selected product (name, price, status, counts). No full catalog and no image bytes.",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_images",
            "description": "List image media_ids for a product (max 3).",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_product_by_url",
            "description": "Find a product by purchase/info URL (0 AI credits).",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_product_by_image",
            "description": "Find 3-8 tenant product candidates from a customer image. If product_name is already clear, name wins and vision is skipped.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_media_id": {"type": "string"},
                    "top_k": {"type": "integer"},
                    "product_name": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["image_media_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_product_context",
            "description": "Read active product context for follow-up questions in this conversation.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_reply_to_product",
            "description": "Resolve product from customer reply-to message id (0 AI credits).",
            "parameters": {
                "type": "object",
                "properties": {"reply_to_message_id": {"type": "string"}},
                "required": ["reply_to_message_id"],
            },
        },
    },
]
