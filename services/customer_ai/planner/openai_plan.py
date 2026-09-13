"""OpenAI structured planner. Invalid JSON / missing key fails closed."""

from __future__ import annotations

import json
from datetime import UTC

from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.generate.reply import openai_configured
from services.customer_ai.planner.heuristic import overlay_plan
from services.customer_ai.providers.config import planner_model


async def plan_with_openai(message: str, history: str = "", *, tenant_id: str = "") -> PlannerPlan | None:
    if not openai_configured():
        return None
    from services.llm_core_service import create_chat_completion

    schema_hint = (
        '{"tasks":[{"id":"t1","type":"information","entity_mentions":[],'
        '"source_families":["services"],"depends_on":[],"missing_fields":[]}],"read_only":true}'
    )
    rules_block = ""
    if tenant_id.strip():
        from services.customer_ai.planner.published_rules import request_rules_prompt_block

        rules_block = request_rules_prompt_block(tenant_id)
    system = (
        "Return JSON only matching PlannerPlan. Task types: information, comparison, "
        "resource_request, hours, service_request, product_request, draft_correction, "
        "cancel_or_status, human_request, acknowledgement. Do not invent entity IDs. "
        "Negated booking or 'I do not want a human' is information, not an action. "
        "Hours, opening time, دوام, يفتح, يسكر, فاتح, or 'when do you close' MUST use "
        'type hours and source_families ["hours","branches"]. Never knowledge-only '
        "for a branch hours question. Keep one task per distinct question."
    )
    if rules_block:
        system += (
            " Honor published tenant request rules exactly: APPOINTMENT → service_request, "
            "ORDER → product_request, HUMAN → human_request. Paraphrases count, not only "
            f"keywords.\n{rules_block}"
        )
    response = await create_chat_completion(
        model=planner_model(),
        messages=[
            {
                "role": "system",
                "content": system,
            },
            {
                "role": "user",
                "content": f"History:\n{history[-4000:]}\n\nMessage:\n{message}\nExample shape:\n{schema_hint}",
            },
        ],
        max_tokens=800,
    )
    raw = ""
    try:
        raw = str(response.choices[0].message.content or "").strip()
    except Exception:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[-1]
    try:
        data = json.loads(raw)
        return PlannerPlan.model_validate(data)
    except Exception:
        return None


async def plan_turn(
    message: str,
    history: str = "",
    *,
    tenant_id: str = "",
    operation_id: str = "",
) -> PlannerPlan:
    planned = await plan_with_openai(message, history, tenant_id=tenant_id)
    if planned is not None and tenant_id.strip():
        from datetime import datetime

        from services.customer_ai.providers.config import planner_model
        from services.membership.provider_expense import record_pending_provider

        op = (operation_id or "planner").strip() or "planner"
        record_pending_provider(
            event_id=f"llm-plan:{tenant_id}:{op}:{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}",
            tenant_id=tenant_id,
            category="llm_generation",
            feature="planning",
            provider="openai",
            model=planner_model(),
            operation_id=op,
        )
    enabled = None
    if tenant_id.strip():
        from services.customer_ai.planner.published_rules import allowed_action_task_types

        enabled = allowed_action_task_types(tenant_id)
    return overlay_plan(planned, message, enabled_action_types=enabled)
