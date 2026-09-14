"""Backward-compatible generation wrapper."""

from __future__ import annotations

from services.smart_followup.generation import generate_followup_text as _generate_followup_text
from services.smart_followup.generation import preview_prompt_for_goal


async def generate_followup_text(
    *,
    tenant_id: str,
    connection_id: str,
    conversation_id: str,
    customer_wa_id: str,
    goal: str,
    profile_name: str = "",
) -> str:
    return await _generate_followup_text(
        tenant_id=tenant_id,
        channel="whatsapp_cloud",
        connection_id=connection_id,
        conversation_id=conversation_id,
        customer_sender_id=customer_wa_id,
        goal=goal,
        profile_name=profile_name,
        user_id=f"whatsapp:{customer_wa_id}",
    )


__all__ = ["generate_followup_text", "preview_prompt_for_goal"]
