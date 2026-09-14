"""Resolve Smart Follow-Up goal keys to instruction prose for Brain compose."""

from __future__ import annotations

from services.smart_followup.generation import GOAL_PROMPTS


def resolve_followup_instruction(goal: str) -> str:
    key = (goal or "").strip()
    if not key:
        return ""
    return (GOAL_PROMPTS.get(key) or GOAL_PROMPTS.get("gentle_check_in") or "").strip()
