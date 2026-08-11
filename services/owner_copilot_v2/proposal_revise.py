"""Helpers for composer Edit-mode proposal revision."""

from __future__ import annotations

from typing import Any


def load_proposal_revise_context(
    *,
    tenant_id: str,
    user_id: str,
    revise_proposal_id: str,
) -> dict[str, Any] | None:
    from services.owner_ai_cm_approval import cm_patch_proposal_store

    prop = cm_patch_proposal_store.get(tenant_id=tenant_id, proposal_id=str(revise_proposal_id))
    if prop is None or prop.user_id != user_id or prop.status != "pending":
        return None
    return {
        "proposal_id": prop.id,
        "section": prop.section,
        "preview": prop.preview,
        "kind": str((prop.preview or {}).get("kind") or ""),
    }


def supersede_revised_proposal(
    *,
    tenant_id: str,
    user_id: str,
    context: dict[str, Any],
    new_proposal_id: str | None,
) -> None:
    revise = context.get("proposal_revise")
    if not isinstance(revise, dict):
        return
    old_id = str(revise.get("proposal_id") or "")
    new_id = str(new_proposal_id or "")
    if not (old_id and new_id and old_id != new_id):
        return
    from services.owner_ai_cm_approval import reject_cm_patch

    try:
        reject_cm_patch(tenant_id=tenant_id, user_id=user_id, proposal_id=old_id)
    except Exception:
        pass
    context["proposal_revise"] = {**revise, "proposal_id": new_id}
