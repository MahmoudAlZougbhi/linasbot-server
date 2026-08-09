"""Owner Copilot tools for FAQ / Smart Answers entitlements + proposals."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from modules.api_security import resolve_permissions
from services.owner_ai_tools_base import ToolResult
from storage.persistent_storage import _DATA_ROOT


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


@dataclass
class SmartAnswerProposal:
    id: str
    tenant_id: str
    user_id: str
    question: str
    answer: str
    language: str
    created_at: float
    status: str = "pending"
    result: dict[str, Any] | None = None


class SmartAnswerProposalStore:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "owner_ai_smart_answer_proposals")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str, proposal_id: str) -> Path:
        d = self._root / tenant_id
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{proposal_id}.json"

    def create(self, prop: SmartAnswerProposal) -> SmartAnswerProposal:
        with self._lock:
            self._path(prop.tenant_id, prop.id).write_text(json.dumps(asdict(prop), ensure_ascii=False), encoding="utf-8")
        return prop

    def get(self, *, tenant_id: str, proposal_id: str) -> SmartAnswerProposal | None:
        path = self._path(tenant_id, proposal_id)
        if not path.is_file():
            return None
        return SmartAnswerProposal(**json.loads(path.read_text(encoding="utf-8")))

    def mark(self, prop: SmartAnswerProposal, *, status: str, result: dict[str, Any] | None = None) -> SmartAnswerProposal:
        prop.status = status
        prop.result = result
        with self._lock:
            self._path(prop.tenant_id, prop.id).write_text(json.dumps(asdict(prop), ensure_ascii=False), encoding="utf-8")
        return prop


smart_answer_proposal_store = SmartAnswerProposalStore()


async def tool_read_faq_quota(*, tenant_id: str, role: str) -> ToolResult:
    del role
    from services.faq_entitlements import get_faq_entitlement
    from services.faq_metrics import faq_metrics_store

    ent = get_faq_entitlement(tenant_id)
    metrics = faq_metrics_store.snapshot(tenant_id)
    return ToolResult(
        ok=True,
        name="read_faq_quota",
        data={"entitlement": ent, "metrics": metrics},
    )


async def tool_propose_smart_answer(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    question: str,
    answer: str,
    language: str = "ar",
) -> ToolResult:
    _require(role, "contentManagers")
    from services.faq_entitlements import FaqEntitlementError, assert_can_create_faq

    q = (question or "").strip()
    a = (answer or "").strip()
    if not q or not a:
        return ToolResult(ok=False, name="propose_smart_answer", data={}, error="question and answer required")
    try:
        assert_can_create_faq(tenant_id)
    except FaqEntitlementError as exc:
        return ToolResult(
            ok=False,
            name="propose_smart_answer",
            data=exc.payload,
            error=str(exc),
        )
    prop = smart_answer_proposal_store.create(
        SmartAnswerProposal(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            user_id=user_id,
            question=q,
            answer=a,
            language=(language or "ar").strip() or "ar",
            created_at=time.time(),
        )
    )
    data = {
        "proposal_id": prop.id,
        "confirmation_token": f"approve_smart_answer:{prop.id}",
        "preview": {"question": q, "answer": a, "language": prop.language},
        "requires_confirmation": True,
        "status": "pending",
    }
    return ToolResult(
        ok=True,
        name="propose_smart_answer",
        data=data,
        requires_confirmation=True,
        confirmation_token=data["confirmation_token"],
        error="Confirmation required before saving Smart Answer",
    )


async def tool_approve_smart_answer(
    *,
    tenant_id: str,
    role: str,
    user_id: str,
    proposal_id: str,
    confirmed: bool,
) -> ToolResult:
    _require(role, "contentManagers")
    if not confirmed:
        return ToolResult(
            ok=True,
            name="approve_smart_answer",
            data={"proposal_id": proposal_id},
            requires_confirmation=True,
            confirmation_token=f"approve_smart_answer:{proposal_id}",
            error="Confirmation required",
        )
    from services.cm.faq_integration import create_faq_pair
    from services.faq_entitlements import FaqEntitlementError, assert_can_create_faq

    prop = smart_answer_proposal_store.get(tenant_id=tenant_id, proposal_id=proposal_id)
    if prop is None:
        return ToolResult(ok=False, name="approve_smart_answer", data={}, error="Proposal not found")
    if prop.user_id != user_id:
        raise PermissionError("Proposal belongs to another user")
    if prop.status != "pending":
        return ToolResult(ok=False, name="approve_smart_answer", data={}, error=f"Not pending ({prop.status})")
    try:
        assert_can_create_faq(tenant_id)
    except FaqEntitlementError as exc:
        return ToolResult(ok=False, name="approve_smart_answer", data=exc.payload, error=str(exc))

    created = await create_faq_pair(
        question=prop.question,
        answer=prop.answer,
        language=prop.language,
        tenant_id=tenant_id,
        updated_by=user_id,
        tags=["smart_answer", "owner_copilot"],
    )
    smart_answer_proposal_store.mark(prop, status="approved", result=created)
    return ToolResult(
        ok=True,
        name="approve_smart_answer",
        data={
            "proposal_id": prop.id,
            "status": "approved",
            "qa_group_id": created.get("qa_group_id"),
            "publish_prompt": False,
        },
    )
