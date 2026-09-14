"""Candidate quality gate before atomic pointer activate. Never activates on failure."""

from __future__ import annotations

from typing import Any


def candidate_is_activatable(*, entity: dict[str, Any], contextual: dict[str, Any]) -> dict[str, Any]:
    entity_reason = str(entity.get("reason") or "")
    ctx_reason = str(contextual.get("reason") or "")
    entity_ok = bool(entity.get("written")) or entity_reason in {"empty_entity", "candidate_built", "ok"}
    if entity.get("written") is False:
        entity_ok = False
    ctx_ok = ctx_reason in {"candidate_built", "no_knowledge_chunks", "ok"} or bool(contextual.get("ready"))
    if contextual.get("ready") is False and ctx_reason not in {"no_knowledge_chunks", "candidate_built"}:
        ctx_ok = False
    if not entity_ok:
        return {"ok": False, "reason": entity.get("reason") or "entity_candidate_failed"}
    if not ctx_ok:
        return {"ok": False, "reason": contextual.get("reason") or "contextual_candidate_failed"}
    return {"ok": True, "reason": "candidate_ready"}
