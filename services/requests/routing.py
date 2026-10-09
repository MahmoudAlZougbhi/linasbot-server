"""Pick the assignee from the owner's request rules."""

from __future__ import annotations


def route_assignee(rules: list[dict[str, str]], *, branch: str, owner_id: str) -> str:
    wanted = (branch or "").strip()
    for rule in rules:
        if str(rule.get("branch") or "").strip() == wanted and str(rule.get("assignee") or "").strip():
            return str(rule["assignee"])
    return owner_id
