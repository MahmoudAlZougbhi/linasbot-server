"""OpenAI structured planner. Invalid JSON / missing key fails closed."""

from __future__ import annotations

import json

from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.generate.reply import openai_configured
from services.customer_ai.planner.heuristic import plan_message
from services.customer_ai.providers.config import planner_model


async def plan_with_openai(message: str) -> PlannerPlan | None:
    if not openai_configured():
        return None
    from services.llm_core_service import create_chat_completion

    schema_hint = (
        '{"tasks":[{"id":"t1","type":"information","entity_mentions":[],'
        '"source_families":["services"],"depends_on":[],"missing_fields":[]}],"read_only":true}'
    )
    response = await create_chat_completion(
        model=planner_model(),
        messages=[
            {
                "role": "system",
                "content": (
                    "Return JSON only matching PlannerPlan. Task types: information, comparison, "
                    "resource_request, hours, service_request, product_request, draft_correction, "
                    "cancel_or_status, human_request, acknowledgement. Do not invent entity IDs."
                ),
            },
            {"role": "user", "content": f"Message:\n{message}\nExample shape:\n{schema_hint}"},
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


async def plan_turn(message: str) -> PlannerPlan:
    planned = await plan_with_openai(message)
    return planned or plan_message(message)
