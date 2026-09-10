"""Grounded final reply. Missing OpenAI is provider_not_configured, not a fake answer."""

from __future__ import annotations

import os

from services.customer_ai.compose.blocks import compose_evidence_context
from services.customer_ai.contracts.evidence import EvidenceBundle
from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.grounding.facts import ungrounded_amounts
from services.customer_ai.identity import IdentityBundle
from services.customer_ai.providers.config import answer_model


def openai_configured() -> bool:
    return bool((os.getenv("OPENAI_API_KEY") or "").strip())


async def generate_grounded_reply(
    *,
    turn: CustomerTurn,
    message: str,
    plan: PlannerPlan,
    bundle: EvidenceBundle,
    identity: IdentityBundle | None,
    destination: str,
    receipts: list[str] | None = None,
) -> FinalReplyEnvelope | None:
    if not openai_configured():
        return None
    context = compose_evidence_context(
        identity=identity,
        plan=plan,
        bundle=bundle,
        receipts=receipts,
        followup_goal=turn.followup_goal,
    )
    history_lines = [f"{item.role}: {item.text}" for item in turn.history.messages]
    prompt = (
        f"{context}\n\nHISTORY\n"
        + "\n".join(history_lines)
        + f"\n\nCURRENT_INBOUND\n{message}\n\nReply in the customer's language. One coherent message."
    )
    from services.llm_core_service import create_chat_completion

    response = await create_chat_completion(
        model=answer_model(),
        messages=[
            {"role": "system", "content": "You are the tenant's customer assistant. Use only provided evidence."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=700,
    )
    text = ""
    try:
        text = str(response.choices[0].message.content or "").strip()
    except Exception:
        text = ""
    if not text or ungrounded_amounts(text, bundle):
        return FinalReplyEnvelope(decision="clarify", messages=[])
    return FinalReplyEnvelope(
        decision="reply",
        messages=[OutboundMessage(destination=destination, text=text)],
        used_evidence_ids=[item.evidence_id for item in bundle.items],
        dispositions={task.id: "answered" for task in plan.tasks if task.type in {"information", "hours", "comparison"}},
    )
