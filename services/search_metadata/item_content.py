"""Full single-item content Luna reads at Save (never the rest of the tenant)."""

from __future__ import annotations

from typing import Any

from services.customer_reply_v2.retrieval_item_index import record_content
from services.search_metadata.luna_titles import original_title_of


def save_time_item_content(section_id: str, raw: dict[str, Any]) -> str:
    """Grounded body of one CM record. AI search fields are not facts and are omitted by record_content."""
    body = record_content(section_id, raw)
    original = original_title_of(raw)
    if original and original not in body[: max(len(original) + 8, 80)]:
        return f"original_title: {original}\n{body}".strip()
    return body
