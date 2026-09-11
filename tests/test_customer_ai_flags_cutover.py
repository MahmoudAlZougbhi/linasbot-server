"""P0 cutover flag matrix: Brain OFF never restores Luna/Terra."""

from __future__ import annotations

import pytest

from services.customer_ai.flags import assert_safe_brain_cutover, emergency_legacy_reply_enabled
from services.customer_ai.tenant_gate import evaluate_brain_tenant_gate
from services.customer_reply_v2.models import ENGINE_REMOVED
from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm


def test_cutover_matrix_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_BRAIN_ENABLED", raising=False)
    monkeypatch.delenv("EMERGENCY_LEGACY_REPLY_ENABLED", raising=False)
    matrix = assert_safe_brain_cutover()
    assert matrix["brain_on"] is False
    assert matrix["brain_off"] is True
    assert matrix["emergency_legacy"] is False
    assert matrix["emergency_legacy_default"] is False
    assert matrix["rollback_required_when_brain_off"] is True
    assert matrix["luna_terra_restored"] is False
    assert matrix["flag_off_stop_reason"] == "engine_removed"
    assert emergency_legacy_reply_enabled() is False


def test_cutover_matrix_emergency_still_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_BRAIN_ENABLED", raising=False)
    monkeypatch.setenv("EMERGENCY_LEGACY_REPLY_ENABLED", "true")
    matrix = assert_safe_brain_cutover()
    assert matrix["emergency_legacy"] is True
    assert matrix["luna_terra_restored"] is False
    assert matrix["flag_off_stop_reason"] == "emergency_legacy_unavailable"


@pytest.mark.asyncio
async def test_brain_off_engine_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_BRAIN_ENABLED", raising=False)
    monkeypatch.delenv("EMERGENCY_LEGACY_REPLY_ENABLED", raising=False)
    out = await run_customer_reply_v2_dm(tenant_id="linas", message="hi")
    assert out.stop is True
    assert out.reply is None
    assert out.reason == ENGINE_REMOVED
    assert out.metadata.get("ai_called") is False


@pytest.mark.asyncio
async def test_brain_off_emergency_legacy_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_BRAIN_ENABLED", raising=False)
    monkeypatch.setenv("EMERGENCY_LEGACY_REPLY_ENABLED", "1")
    out = await run_customer_reply_v2_dm(tenant_id="linas", message="hi")
    assert out.stop is True
    assert out.reply is None
    assert out.reason == "emergency_legacy_unavailable"
    assert out.metadata.get("ai_called") is False
    assert out.metadata.get("rollback_required") is True


def test_default_allowlist_includes_linas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_BRAIN_TENANT_ALLOWLIST", raising=False)
    gate = evaluate_brain_tenant_gate("linas")
    assert gate["allow"] is True
    assert gate["path"] == "allowlist"


def test_lab_tenant_requires_lab_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINAS_CUSTOMER_AI_LAB", raising=False)
    denied = evaluate_brain_tenant_gate("lab_demo")
    assert denied["allow"] is False
    assert denied["reason"] == "brain_gates_incomplete"
    monkeypatch.setenv("LINAS_CUSTOMER_AI_LAB", "true")
    allowed = evaluate_brain_tenant_gate("lab_demo")
    assert allowed["allow"] is True
    assert allowed["path"] == "lab"


def test_non_allowlist_denied_even_when_testing_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """testing_ready is import-only — must not unlock arbitrary customer tenants."""
    monkeypatch.setenv("CUSTOMER_BRAIN_TENANT_ALLOWLIST", "other-shop")
    monkeypatch.setattr(
        "services.membership.activation_readiness.activation_readiness",
        lambda: {"testing_ready": True, "testing_blockers": []},
    )
    denied = evaluate_brain_tenant_gate("unknown-tenant")
    assert denied["allow"] is False
    assert denied["reason"] == "brain_gates_incomplete"
    assert denied["path"] == "not_allowlisted"
    # Allowlisted tenant still passes without needing testing_ready.
    allowed = evaluate_brain_tenant_gate("other-shop")
    assert allowed["allow"] is True
    assert allowed["path"] == "allowlist"


@pytest.mark.asyncio
async def test_search_readiness_requires_tenant_pointer(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.search.readiness import search_readiness
    from services.customer_ai.search.store import activate_pointer, reset_memory_store

    monkeypatch.setenv("VOYAGE_API_KEY", "sk-test")
    reset_memory_store()
    missing = search_readiness(session=None, tenant_id="shop-a")
    assert missing.ready is False
    assert missing.reason == "index_not_ready"
    assert missing.pointer_ready is False
    activate_pointer(
        None,
        tenant_id="shop-a",
        space_id="space",
        source_family="knowledge",
        version="v1",
        count=1,
    )
    ready = search_readiness(session=None, tenant_id="shop-a")
    assert ready.ready is True
    assert ready.pointer_ready is True
    assert ready.reason == "ok"
