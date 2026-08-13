"""AI text generation for follow-up steps via Customer Reply V2."""

from __future__ import annotations

from typing import Any

from services.smart_followup.channels import normalize_followup_channel

GOAL_PROMPTS: dict[str, str] = {
    "gentle_check_in": (
        "The customer has not replied to your last support message. "
        "Write a brief, gentle check-in in the customer's language. "
        "Stay customer-support oriented. Do not invent orders, appointments, prices, "
        "availability, discounts, or promotions. Do not market. Keep it concise and natural."
    ),
    "offer_more_help": (
        "The customer still has not replied. Offer more help briefly in the customer's language. "
        "Ask if they still need assistance with their earlier question. "
        "Do not invent business data, prices, appointments, or promotions. No marketing."
    ),
    "politely_close": (
        "The customer has not replied after earlier follow-ups. Write a polite, short closing note "
        "in the customer's language saying you remain available if they need help later. "
        "Do not invent data or promotions. No marketing. Do not pressure them."
    ),
}

_CHANNEL_LABELS = {
    "whatsapp_cloud": "WhatsApp",
    "instagram_dm": "Instagram DM",
    "facebook_messenger": "Facebook Messenger",
}


async def generate_followup_text(
    *,
    tenant_id: str,
    channel: str,
    connection_id: str,
    conversation_id: str,
    customer_sender_id: str,
    goal: str,
    profile_name: str = "",
    user_id: str = "",
) -> str:
    normalized = normalize_followup_channel(channel)
    prompt = GOAL_PROMPTS.get(goal) or GOAL_PROMPTS["gentle_check_in"]
    label = _CHANNEL_LABELS.get(normalized, "DM")
    message = (
        f"[Smart Follow-Up / {goal}]\n{prompt}\nRespond with only the {label} message text to send to the customer."
    )
    cr_channel = normalized
    if normalized == "whatsapp_cloud":
        cr_channel = "whatsapp_dm"
    elif normalized == "facebook_messenger":
        cr_channel = "facebook_dm"

    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    outcome = await run_customer_reply_v2_dm(
        tenant_id=tenant_id,
        message=message,
        detected_language="",
        response_language="",
        channel=cr_channel,
        asset_id=connection_id,
        provider_sender_id=customer_sender_id,
        provider_display_name=profile_name or "",
        user_id=user_id or customer_sender_id,
        conversation_id=conversation_id,
    )
    reply_text = str(
        getattr(outcome, "reply", None) or getattr(outcome, "answer", None) or getattr(outcome, "text", None) or ""
    ).strip()
    if not reply_text and isinstance(outcome, dict):
        reply_text = str(outcome.get("reply") or outcome.get("answer") or outcome.get("text") or "").strip()
    return reply_text


def preview_prompt_for_goal(goal: str) -> dict[str, Any]:
    return {
        "goal": goal if goal in GOAL_PROMPTS else "gentle_check_in",
        "instruction": GOAL_PROMPTS.get(goal) or GOAL_PROMPTS["gentle_check_in"],
        "sends_message": False,
        "uses_credits": True,
        "writer": "customer_reply_v2",
    }
