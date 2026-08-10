"""Owner self-diagnosis: find bad replies, explain root cause, propose + apply fixes."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from storage.persistent_storage import _DATA_ROOT

_SESSION_RE = re.compile(
    r"\b(\d+)\s*(?:-|–|to|إلى)?\s*(\d+)?\s*(?:session|sessions|جلسة|جلسات|séance|séances)\b",
    re.I,
)
_LOCATION_RE = re.compile(r"\b(location|address|branch|موقع|عنوان|localisation)\b", re.I)
_SERVICE_RE = re.compile(r"\b(service|treatment|علاج|خدمة|prestation)\b", re.I)


@dataclass
class DiagnosisProposal:
    id: str
    tenant_id: str
    user_id: str
    trace_id: str
    root_cause: str
    explanation: str
    correction: dict[str, Any]
    created_at: float
    status: str = "pending"
    result: dict[str, Any] | None = None


class DiagnosisProposalStore:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "owner_ai_diagnosis_proposals")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str, proposal_id: str) -> Path:
        d = self._root / tenant_id
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{proposal_id}.json"

    def create(self, prop: DiagnosisProposal) -> DiagnosisProposal:
        with self._lock:
            self._path(prop.tenant_id, prop.id).write_text(
                json.dumps(asdict(prop), ensure_ascii=False), encoding="utf-8"
            )
        return prop

    def get(self, *, tenant_id: str, proposal_id: str) -> DiagnosisProposal | None:
        path = self._path(tenant_id, proposal_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return DiagnosisProposal(**data)

    def mark(self, prop: DiagnosisProposal, *, status: str, result: dict[str, Any] | None = None) -> DiagnosisProposal:
        prop.status = status
        prop.result = result
        with self._lock:
            self._path(prop.tenant_id, prop.id).write_text(
                json.dumps(asdict(prop), ensure_ascii=False), encoding="utf-8"
            )
        return prop

    def latest_pending(self, *, tenant_id: str, user_id: str) -> DiagnosisProposal | None:
        best: DiagnosisProposal | None = None
        d = self._root / tenant_id
        if not d.is_dir():
            return None
        with self._lock:
            paths = list(d.glob("*.json"))
        for path in paths:
            prop = self.get(tenant_id=tenant_id, proposal_id=path.stem)
            if prop is None or prop.user_id != user_id or prop.status != "pending":
                continue
            if best is None or prop.created_at >= best.created_at:
                best = prop
        return best


diagnosis_proposal_store = DiagnosisProposalStore()


def _scenario_from_trace(trace: dict[str, Any]) -> str:
    msg = f"{trace.get('customer_message') or ''} {trace.get('ai_response') or ''}"
    if _SESSION_RE.search(msg):
        return "session_count"
    if _LOCATION_RE.search(msg):
        return "location"
    if _SERVICE_RE.search(msg):
        return "service"
    if isinstance(trace.get("faq_match"), dict) and trace.get("faq_match"):
        return "stale_faq"
    return "general_cm_mismatch"


def diagnose_interaction(*, tenant_id: str, trace_id: str) -> dict[str, Any]:
    """Explain root cause for a bad customer reply using TRACE evidence (no CoT)."""
    from services.customer_response_trace import get_interaction_trace

    trace = get_interaction_trace(tenant_id=tenant_id, trace_id=trace_id)
    if not trace:
        raise ValueError("Interaction trace not found for this tenant")

    scenario = _scenario_from_trace(trace)
    faq = trace.get("faq_match") if isinstance(trace.get("faq_match"), dict) else None
    cm_refs = trace.get("cm_refs") if isinstance(trace.get("cm_refs"), dict) else {}
    retrieved = list(trace.get("retrieved_sections") or [])

    if scenario == "session_count":
        root = "session_count_mismatch"
        explanation = (
            "Customer asked about session count; the reply likely used a stale FAQ or CM services "
            "value (e.g. '7 sessions' while current truth is a range like '7–10')."
        )
        correction = {
            "type": "cm_patch",
            "section": "services",
            "patch_hint": {"sessions_note": "Update session range to current truth (e.g. 7-10)."},
            "also_invalidate_faq": True,
        }
    elif scenario == "location":
        root = "bad_location"
        explanation = (
            "Reply location does not match current CM locations/basics. "
            "Likely stale FAQ match or wrong retrieved location source."
        )
        correction = {
            "type": "cm_patch",
            "section": "locations",
            "patch_hint": {"address": "Replace with the correct business location from owner."},
            "also_invalidate_faq": True,
        }
    elif scenario == "service":
        root = "wrong_service"
        explanation = (
            "Reply referenced the wrong service. TRACE retrieved sections/FAQ did not align "
            "with the customer's service intent."
        )
        correction = {
            "type": "cm_patch",
            "section": "services",
            "patch_hint": {"service_name": "Align service catalog entry with owner correction."},
            "also_invalidate_faq": True,
        }
    elif scenario == "stale_faq":
        root = "stale_faq_match"
        explanation = (
            f"Smart Answer fast-path matched FAQ (id={faq.get('faq_id') if faq else None}) "
            "but content is no longer consistent with CM."
        )
        correction = {
            "type": "faq_update",
            "qa_group_id": (faq or {}).get("qa_group_id"),
            "faq_id": (faq or {}).get("faq_id"),
            "patch_hint": {"answer": "Replace with owner-approved correct answer."},
        }
    else:
        root = "general_mismatch"
        explanation = (
            "Reply does not match current published/draft CM facts. "
            f"Retrieved refs={retrieved[:5]}; cm_version={(cm_refs or {}).get('content_version_id')}."
        )
        correction = {
            "type": "cm_patch",
            "section": "basics",
            "patch_hint": {},
            "also_invalidate_faq": False,
        }

    return {
        "trace_id": trace_id,
        "tenant_id": tenant_id,
        "scenario": scenario,
        "root_cause": root,
        "explanation": explanation,
        "evidence": {
            "customer_message": trace.get("customer_message"),
            "ai_response": trace.get("ai_response"),
            "faq_match": faq,
            "cm_refs": cm_refs,
            "retrieved_sections": retrieved,
            "model": trace.get("model"),
            "tools_used": trace.get("tools_used") or [],
            "source": trace.get("source"),
        },
        "proposed_correction": correction,
    }


def propose_diagnosis_fix(
    *,
    tenant_id: str,
    user_id: str,
    trace_id: str,
    correction_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnosis = diagnose_interaction(tenant_id=tenant_id, trace_id=trace_id)
    correction = dict(diagnosis["proposed_correction"])
    if correction_override:
        correction.update(correction_override)
    prop = DiagnosisProposal(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        user_id=user_id,
        trace_id=trace_id,
        root_cause=str(diagnosis["root_cause"]),
        explanation=str(diagnosis["explanation"]),
        correction=correction,
        created_at=time.time(),
    )
    diagnosis_proposal_store.create(prop)
    return {
        "proposal_id": prop.id,
        "confirmation_token": f"approve_diagnosis_fix:{prop.id}",
        "requires_confirmation": True,
        "diagnosis": diagnosis,
        "correction": correction,
        "status": "pending",
    }


async def approve_diagnosis_fix(
    *,
    tenant_id: str,
    user_id: str,
    proposal_id: str,
) -> dict[str, Any]:
    """Apply correction immediately after approval — no Publish UX."""
    prop = diagnosis_proposal_store.get(tenant_id=tenant_id, proposal_id=proposal_id)
    if prop is None:
        raise ValueError("Diagnosis proposal not found")
    if prop.user_id != user_id:
        raise PermissionError("Proposal belongs to another user")
    if prop.status != "pending":
        raise ValueError(f"Proposal is not pending ({prop.status})")

    corr = dict(prop.correction or {})
    applied: dict[str, Any] = {"type": corr.get("type")}

    if corr.get("type") == "faq_update":
        from services.cm.faq_integration import create_faq_pair, update_cm_faq_variant

        qa_group_id = corr.get("qa_group_id")
        answer = str((corr.get("patch") or corr.get("patch_hint") or {}).get("answer") or "").strip()
        question = str((corr.get("patch") or corr.get("patch_hint") or {}).get("question") or "").strip()
        if qa_group_id and answer:
            updated = await update_cm_faq_variant(
                qa_group_id=str(qa_group_id),
                language=str(corr.get("language") or "ar"),
                question=question or None,
                answer=answer,
                reviewed=True,
                tenant_id=tenant_id,
                updated_by=user_id,
            )
            applied["faq"] = {"qa_group_id": qa_group_id, "updated": True, "result": updated.get("success", True)}
        elif question and answer:
            created = await create_faq_pair(
                question=question,
                answer=answer,
                language=str(corr.get("language") or "ar"),
                tenant_id=tenant_id,
                updated_by=user_id,
                tags=["diagnosis_fix"],
            )
            applied["faq"] = {"created": True, "qa_group_id": created.get("qa_group_id")}
        else:
            raise ValueError("FAQ correction requires answer (and qa_group_id or question)")
    else:
        from services.cm.constants import tenant_has_published_cm
        from services.cm.setup_chat import apply_section_patch
        from services.faq_cm_invalidation import invalidate_faq_for_cm_patch
        from services.owner_ai_cm_approval import activate_cm_after_save

        section = str(corr.get("section") or "services")
        patch = dict(corr.get("patch") or corr.get("patch_hint") or {})
        if not patch:
            raise ValueError("CM correction requires a concrete patch from the owner")
        saved = apply_section_patch(
            tenant_id=tenant_id,
            section=section,
            patch=patch,
            actor_id=user_id,
        )
        applied["cm"] = {
            "section": section,
            "revision": saved.get("revision"),
            "etag": saved.get("etag"),
        }
        if corr.get("also_invalidate_faq"):
            applied["faq_invalidation"] = invalidate_faq_for_cm_patch(
                tenant_id=tenant_id,
                section=section,
                patch=patch,
                cm_revision=saved.get("revision"),
            )
        if tenant_has_published_cm(tenant_id):
            applied["activation"] = await activate_cm_after_save(
                tenant_id=tenant_id,
                section=section,
                actor_id=user_id,
            )

    diagnosis_proposal_store.mark(prop, status="approved", result=applied)
    return {
        "proposal_id": prop.id,
        "status": "approved",
        "trace_id": prop.trace_id,
        "root_cause": prop.root_cause,
        "applied": applied,
        "publish_prompt": False,
    }
