"""CM write path: propose patch → human preview → approval → validate → save.

Never auto-writes CM from raw LLM output without an explicit approval token.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT


@dataclass
class ProposedCmPatch:
    id: str
    tenant_id: str
    user_id: str
    section: str
    patch: dict[str, Any]
    preview: dict[str, Any]
    created_at: float
    status: str = "pending"  # pending | approved | rejected | expired
    result: dict[str, Any] | None = None


class CmPatchProposalStore:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "owner_ai_cm_proposals")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str, proposal_id: str) -> Path:
        d = self._root / tenant_id
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{proposal_id}.json"

    def create(
        self,
        *,
        tenant_id: str,
        user_id: str,
        section: str,
        patch: dict[str, Any],
        preview: dict[str, Any],
    ) -> ProposedCmPatch:
        prop = ProposedCmPatch(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            user_id=user_id,
            section=section,
            patch=patch,
            preview=preview,
            created_at=time.time(),
        )
        self._write(prop)
        return prop

    def get(self, *, tenant_id: str, proposal_id: str) -> ProposedCmPatch | None:
        path = self._path(tenant_id, proposal_id)
        with self._lock:
            if not path.is_file():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return ProposedCmPatch(
            id=str(data["id"]),
            tenant_id=str(data["tenant_id"]),
            user_id=str(data["user_id"]),
            section=str(data["section"]),
            patch=dict(data.get("patch") or {}),
            preview=dict(data.get("preview") or {}),
            created_at=float(data.get("created_at") or 0),
            status=str(data.get("status") or "pending"),
            result=data.get("result") if isinstance(data.get("result"), dict) else None,
        )

    def _write(self, prop: ProposedCmPatch) -> None:
        path = self._path(prop.tenant_id, prop.id)
        with self._lock:
            path.write_text(json.dumps(asdict(prop), ensure_ascii=False), encoding="utf-8")

    def mark(self, prop: ProposedCmPatch, *, status: str, result: dict[str, Any] | None = None) -> ProposedCmPatch:
        prop.status = status
        prop.result = result
        self._write(prop)
        return prop


cm_patch_proposal_store = CmPatchProposalStore()


def build_patch_preview(*, tenant_id: str, section: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Show current vs proposed merge without saving."""
    from services.cm.constants import CM_SECTIONS
    from services.cm.setup_chat import _merge_dict
    from services.cm.storage import get_draft

    name = section.strip().replace("-", "_")
    if name not in CM_SECTIONS:
        raise ValueError(f"Unknown CM section: {section}")
    if not isinstance(patch, dict):
        raise ValueError("Patch must be an object")
    forbidden = {"tenant_id", "permissions", "role", "platform_rules"}
    bad = forbidden.intersection(patch.keys())
    if bad:
        raise ValueError(f"Forbidden patch fields: {sorted(bad)}")

    env = get_draft(name, tenant_id=tenant_id, create_default=True)
    current = dict(env.payload) if isinstance(env.payload, dict) else {}
    merged = _merge_dict(current, patch)
    changed_keys = sorted(k for k in patch.keys() if current.get(k) != merged.get(k))
    return {
        "section": name,
        "changed_keys": changed_keys,
        "current_sample": {k: current.get(k) for k in changed_keys[:12]},
        "proposed_sample": {k: merged.get(k) for k in changed_keys[:12]},
        "patch": patch,
        "revision": getattr(env, "revision", None),
    }


def propose_cm_patch(
    *,
    tenant_id: str,
    user_id: str,
    section: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    preview = build_patch_preview(tenant_id=tenant_id, section=section, patch=patch)
    prop = cm_patch_proposal_store.create(
        tenant_id=tenant_id,
        user_id=user_id,
        section=preview["section"],
        patch=patch,
        preview=preview,
    )
    return {
        "proposal_id": prop.id,
        "confirmation_token": f"approve_cm_patch:{prop.id}",
        "preview": preview,
        "status": prop.status,
        "requires_confirmation": True,
    }


def approve_cm_patch(
    *,
    tenant_id: str,
    user_id: str,
    proposal_id: str,
    actor_id: str | None = None,
) -> dict[str, Any]:
    prop = cm_patch_proposal_store.get(tenant_id=tenant_id, proposal_id=proposal_id)
    if prop is None:
        raise ValueError("Proposal not found")
    if prop.user_id != user_id:
        raise PermissionError("Proposal belongs to another user")
    if prop.status != "pending":
        raise ValueError(f"Proposal is not pending ({prop.status})")

    from services.cm.setup_chat import apply_section_patch
    from services.cm.validation import validate_cm

    saved = apply_section_patch(
        tenant_id=tenant_id,
        section=prop.section,
        patch=prop.patch,
        actor_id=actor_id or user_id,
    )
    report = validate_cm(tenant_id=tenant_id, section=prop.section)
    result = {"saved": saved, "validation": report}
    cm_patch_proposal_store.mark(prop, status="approved", result=result)
    return {
        "proposal_id": prop.id,
        "status": "approved",
        "section": prop.section,
        "saved": {
            "revision": saved.get("revision"),
            "etag": saved.get("etag"),
            "section": saved.get("section"),
        },
        "validation": {
            "ok": not bool((report or {}).get("errors")),
            "error_count": len((report or {}).get("errors") or []),
            "warning_count": len((report or {}).get("warnings") or []),
        },
    }


def reject_cm_patch(*, tenant_id: str, user_id: str, proposal_id: str) -> dict[str, Any]:
    prop = cm_patch_proposal_store.get(tenant_id=tenant_id, proposal_id=proposal_id)
    if prop is None:
        raise ValueError("Proposal not found")
    if prop.user_id != user_id:
        raise PermissionError("Proposal belongs to another user")
    cm_patch_proposal_store.mark(prop, status="rejected", result={"rejected": True})
    return {"proposal_id": prop.id, "status": "rejected"}
