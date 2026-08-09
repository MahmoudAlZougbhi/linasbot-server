"""Phase-2B: diagnosis TRACE, FAQ entitlements/quota/isolation, CM approve no-publish UX."""

from __future__ import annotations

from typing import Any

import pytest

from services.customer_response_trace import (
    CustomerResponseTraceStore,
    build_safe_trace,
    get_interaction_trace,
    get_recent_customer_interactions,
)
from services.faq_cm_invalidation import extract_session_markers
from services.faq_entitlements import FaqEntitlementError, assert_can_create_faq, get_faq_entitlement
from services.faq_metrics import FaqMetricsStore
from services.faq_safe_match import find_safe_faq_match, score_candidate
from services.owner_ai_cm_approval import CmPatchProposalStore, approve_cm_patch, propose_cm_patch
from services.owner_ai_diagnosis import diagnose_interaction, propose_diagnosis_fix
from services.owner_ai_model_router import OwnerChatUsageTracker, route_owner_turn
from services.plan_economics import PLAN_FAQ_MAX_ENTRIES, PLAN_FEATURES
from services.system_knowledge_registry import get_capability, registry_route_errors


def test_registry_includes_faq_and_diagnosis_routes() -> None:
    assert registry_route_errors() == []
    assert get_capability("smart_answers_faq") is not None
    assert get_capability("self_diagnosis") is not None
    assert "get_interaction_trace" in (get_capability("self_diagnosis").tools or ())


def test_faq_entitlements_central_plan_config(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from services import entitlements_service as es
    from services import faq_entitlements as fe
    from services.entitlements_service import EntitlementsStore

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr(fe, "count_faq_entries", lambda _tid: 0)

    assert PLAN_FEATURES["starter"]["faq_enabled"] is True
    assert PLAN_FAQ_MAX_ENTRIES["starter"] == 200
    assert PLAN_FAQ_MAX_ENTRIES["pro"] == 1000
    assert PLAN_FAQ_MAX_ENTRIES["none"] == 0

    none = get_faq_entitlement("t-none")
    assert none["faq_enabled"] is False
    assert none["faq_max_entries"] == 0

    store.set_plan(tenant_id="t1", plan_id="starter", status="active", source="admin")
    starter = get_faq_entitlement("t1")
    assert starter["faq_enabled"] is True
    assert starter["faq_max_entries"] == 200
    assert starter["quota_display"] == "0 / 200"

    monkeypatch.setattr(fe, "count_faq_entries", lambda _tid: 200)
    at_limit = get_faq_entitlement("t1")
    assert at_limit["at_limit"] is True
    with pytest.raises(FaqEntitlementError) as exc:
        assert_can_create_faq("t1")
    assert exc.value.code == "FAQ_QUOTA_EXCEEDED"
    assert "Upgrade" in str(exc.value)


def test_faq_tenant_isolation_safe_match(monkeypatch: pytest.MonkeyPatch) -> None:
    pairs = [
        {
            "tenant_id": "tenant_a",
            "question": "How many sessions do I need?",
            "answer": "You need 7 sessions.",
            "language": "en",
            "is_active": True,
            "status": "active",
            "qa_group_id": "qa_a",
        },
        {
            "tenant_id": "tenant_b",
            "question": "How many sessions do I need?",
            "answer": "You need 7-10 sessions.",
            "language": "en",
            "is_active": True,
            "status": "active",
            "qa_group_id": "qa_b",
        },
    ]
    monkeypatch.setattr(
        "services.faq_entitlements.get_faq_entitlement",
        lambda _tid: {"faq_enabled": True},
    )
    hit_a = find_safe_faq_match(
        tenant_id="tenant_a",
        question="How many sessions do I need?",
        language="en",
        qa_pairs=pairs,
    )
    hit_b = find_safe_faq_match(
        tenant_id="tenant_b",
        question="How many sessions do I need?",
        language="en",
        qa_pairs=pairs,
    )
    assert hit_a is not None
    assert hit_a["qa_pair"]["qa_group_id"] == "qa_a"
    assert hit_b is not None
    assert hit_b["qa_pair"]["qa_group_id"] == "qa_b"


def test_safe_match_rejects_stale_and_blind_similarity(monkeypatch: pytest.MonkeyPatch) -> None:
    stale = {
        "tenant_id": "t1",
        "question": "Where is the clinic located?",
        "answer": "Old street 1",
        "language": "en",
        "status": "needs_review",
        "cm_stale": True,
        "is_active": True,
    }
    scored = score_candidate(
        question="Where is the clinic located?",
        language="en",
        entry=stale,
        intent="location",
    )
    assert scored["accept"] is False

    monkeypatch.setattr(
        "services.faq_entitlements.get_faq_entitlement",
        lambda _tid: {"faq_enabled": True},
    )
    miss = find_safe_faq_match(
        tenant_id="t1",
        question="Where is the clinic located?",
        language="en",
        qa_pairs=[stale],
    )
    assert miss is None


def test_cm_session_invalidation_markers() -> None:
    assert "7-10" in extract_session_markers("Recommended 7-10 sessions")
    assert "7" in extract_session_markers("7 sessions package")


@pytest.mark.asyncio
async def test_cm_approve_no_publish_prompt(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    store = CmPatchProposalStore(root=tmp_path / "proposals")
    monkeypatch.setattr("services.owner_ai_cm_approval.cm_patch_proposal_store", store)
    monkeypatch.setattr(
        "services.owner_ai_cm_approval.build_patch_preview",
        lambda **_: {
            "section": "services",
            "changed_keys": ["sessions_note"],
            "current_sample": {"sessions_note": "7 sessions"},
            "proposed_sample": {"sessions_note": "7-10 sessions"},
            "patch": {"sessions_note": "7-10 sessions"},
            "revision": 1,
        },
    )
    monkeypatch.setattr(
        "services.cm.setup_chat.apply_section_patch",
        lambda **_: {"section": "services", "revision": 2, "etag": "e2"},
    )
    monkeypatch.setattr(
        "services.cm.validation.validate_cm",
        lambda **_: {"errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        "services.faq_cm_invalidation.invalidate_faq_for_cm_patch",
        lambda **_: {"stale_groups": ["qa_x"], "stale_rows": 1, "reason": "session_markers_changed:7-10"},
    )

    proposed = propose_cm_patch(
        tenant_id="t1",
        user_id="u1",
        section="services",
        patch={"sessions_note": "7-10 sessions"},
    )
    result = approve_cm_patch(tenant_id="t1", user_id="u1", proposal_id=proposed["proposal_id"])
    assert result["status"] == "approved"
    assert result["publish_prompt"] is False
    assert result["faq_invalidation"]["stale_groups"] == ["qa_x"]


def test_diagnosis_session_location_service_scenarios(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    store = CustomerResponseTraceStore(root=tmp_path / "traces")
    monkeypatch.setattr("services.customer_response_trace.customer_response_trace_store", store)

    cases = [
        ("tr_sess", "How many sessions?", "You need 7 sessions.", "session_count_mismatch"),
        ("tr_loc", "What is your location?", "We are on Wrong Street.", "bad_location"),
        ("tr_svc", "Do you offer laser service?", "We offer haircut only.", "wrong_service"),
    ]
    for tid, q, a, root in cases:
        trace = build_safe_trace(
            tenant_id="clinic1",
            channel="instagram",
            conversation_id="c1",
            customer_message=q,
            ai_response=a,
            interaction_id=tid,
            source="gpt",
            model="gpt-4o-mini",
            tools_used=[],
        )
        store.persist(trace)
        diag = diagnose_interaction(tenant_id="clinic1", trace_id=tid)
        assert diag["root_cause"] == root
        assert diag["evidence"]["customer_message"] == q

    recent = get_recent_customer_interactions(tenant_id="clinic1", limit=10)
    assert len(recent) >= 3
    assert get_interaction_trace(tenant_id="clinic1", trace_id="tr_sess") is not None
    # Isolation
    assert get_interaction_trace(tenant_id="other", trace_id="tr_sess") is None


def test_diagnosis_propose_requires_approval(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from services import owner_ai_diagnosis as od

    store = CustomerResponseTraceStore(root=tmp_path / "traces")
    monkeypatch.setattr("services.customer_response_trace.customer_response_trace_store", store)
    prop_store = od.DiagnosisProposalStore(root=tmp_path / "diag")
    monkeypatch.setattr(od, "diagnosis_proposal_store", prop_store)

    store.persist(
        build_safe_trace(
            tenant_id="t1",
            channel="whatsapp",
            conversation_id="c",
            customer_message="How many sessions?",
            ai_response="7 sessions",
            interaction_id="t1",
        )
    )
    proposed = propose_diagnosis_fix(tenant_id="t1", user_id="u1", trace_id="t1")
    assert proposed["requires_confirmation"] is True
    assert proposed["confirmation_token"].startswith("approve_diagnosis_fix:")


def test_faq_metrics_and_token_cost_smoke(tmp_path: Any) -> None:
    metrics = FaqMetricsStore(root=tmp_path / "m")
    metrics.record_lookup(tenant_id="t1", hit=True, generation_avoided=True)
    metrics.record_lookup(tenant_id="t1", hit=False)
    # snapshot needs entitlement; use record totals directly
    raw = metrics._load("t1")
    assert raw["faq_hits"] == 1
    assert raw["generations_avoided"] == 1
    assert raw["misses"] == 1

    tracker = OwnerChatUsageTracker(root=tmp_path / "usage")
    decision = route_owner_turn("diagnose bad reply", intent="get_recent_customer_interactions")
    tracker.record(
        tenant_id="t1",
        user_id="u1",
        conversation_id="c1",
        route=decision,
        prompt_tokens=100,
        completion_tokens=40,
    )
    totals = tracker.totals("t1")
    assert totals["turns"] == 1
    assert totals["total_tokens"] == 140


@pytest.mark.asyncio
async def test_owner_turn_diagnosis_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_ai_orchestrator import run_owner_turn
    from services.owner_ai_tools_base import ToolResult

    monkeypatch.setenv("OWNER_COPILOT_V2", "false")
    monkeypatch.setattr(
        "services.owner_ai_context.pack_owner_turn_context",
        lambda **_: {
            "system_prompt": "x",
            "account_summary": {"setup_stage": "ready", "profile": {"preferred_language": "en"}},
            "knowledge_block": "",
            "capabilities": ["self_diagnosis"],
            "recent_messages": [],
            "conversation_summary": None,
            "reply_language": "en",
            "preferred_language": "en",
            "cm_full_dump": False,
            "full_history": False,
        },
    )
    monkeypatch.setattr("services.owner_ai_model_router.owner_chat_usage_tracker.record", lambda **_: {})

    async def _dispatch(name: str, **kwargs: Any) -> ToolResult:
        del kwargs
        assert name == "get_recent_customer_interactions"
        return ToolResult(ok=True, name=name, data={"interactions": [], "count": 0})

    monkeypatch.setattr("services.owner_ai_tools.dispatch_tool", _dispatch)
    turn = await run_owner_turn(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="That was a bad reply — diagnose it",
    )
    assert turn.tool_calls
    assert turn.tool_calls[0]["name"] == "get_recent_customer_interactions"


def test_rtl_i18n_keys_present() -> None:
    from pathlib import Path

    ar = Path("mobile/linas-ai/src/i18n/locales/ar.ts").read_text(encoding="utf-8")
    en = Path("mobile/linas-ai/src/i18n/locales/en.ts").read_text(encoding="utf-8")
    fr = Path("mobile/linas-ai/src/i18n/locales/fr.ts").read_text(encoding="utf-8")
    for blob in (ar, en, fr):
        assert "faqQuota" in blob
        assert "smartAnswers" in blob
        assert "diagnoseBadReply" in blob
