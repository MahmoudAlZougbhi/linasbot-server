"""Consume owner V2 event stream into a single turn result (line-limit split from brain.py)."""

from __future__ import annotations

from contextlib import aclosing
from typing import Any

from services.owner_copilot_v2.flags import owner_model_name
from services.owner_copilot_v2.models import OwnerV2TurnResult
from services.owner_copilot_v2.turn_results import owner_result_from_done_payload, record_owner_v2_usage


async def run_owner_turn_v2(**kwargs: Any) -> OwnerV2TurnResult:
    from services.owner_copilot_v2.brain import iter_owner_turn_v2_events

    final: OwnerV2TurnResult | None = None
    async with aclosing(iter_owner_turn_v2_events(**kwargs)) as stream:
        async for ev in stream:
            if ev.type == "done":
                final = owner_result_from_done_payload(ev.payload)
                record_owner_v2_usage(kwargs, final)
            elif ev.type == "cancelled":
                return OwnerV2TurnResult(
                    reply_text=str(ev.payload.get("reply_text") or ""),
                    cancelled=True,
                    model=owner_model_name(),
                )
            elif ev.type == "credits_paused" and final is None:
                return OwnerV2TurnResult(
                    reply_text="",
                    route={"reason": "insufficient_credits", **ev.payload},
                    model=owner_model_name(),
                )
            elif ev.type == "error" and final is None:
                return OwnerV2TurnResult(
                    reply_text=str(ev.payload.get("message") or "Linas AI is temporarily unavailable. Please retry."),
                    model=owner_model_name(),
                )
    return final or OwnerV2TurnResult(reply_text="", model=owner_model_name())
