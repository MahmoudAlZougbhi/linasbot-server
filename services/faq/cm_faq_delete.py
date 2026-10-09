"""Hard-delete one FAQ group from the CM draft."""

from __future__ import annotations

from typing import Any

from services.ai_setup.schemas import FaqSection
from services.ai_setup.storage import get_draft, put_draft
from services.faq.cm_faq_helpers import FAQ_SECTION, FaqIntegrationError, faq_section_payload


def delete_cm_faq_group(
    *,
    qa_group_id: str,
    tenant_id: str | None = None,
    updated_by: str = "content_manager",
) -> dict[str, Any]:
    env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    section = FaqSection.model_validate(env.payload)
    kept = [item for item in section.items if item.qa_group_id != qa_group_id]
    if len(kept) == len(section.items):
        raise FaqIntegrationError(f"FAQ group not found: {qa_group_id}")
    put_draft(
        FAQ_SECTION,
        payload=faq_section_payload(
            items=kept,
            notes=section.notes,
            smart_answer_languages=section.smart_answer_languages,
        ),
        if_match=env.etag,
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    return {"success": True, "qa_group_id": qa_group_id, "deleted": True}
