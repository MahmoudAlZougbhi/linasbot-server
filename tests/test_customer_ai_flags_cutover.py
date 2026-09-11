"""Cutover tests after CUSTOMER_BRAIN_ENABLED removal — Brain is permanent."""

from __future__ import annotations

import pytest

from services.customer_ai.flags import assert_safe_brain_cutover, emergency_legacy_reply_enabled
from services.customer_ai.tenant_gate import evaluate_brain_tenant_gate
from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm


def test_cutover_brain_permanent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMERGENCY_LEGACY_REPLY_ENABLED", raising=False)
    matrix = assert_safe_brain_cutover()
    assert matrix["brain_permanent"] is True
    assert matrix["enable_flag_removed"] is True
    assert matrix["luna_terra_restored"] is False
    assert emergency_legacy_reply_enabled() is False


def test_tenant_gate_allows_any_tenant() -> None:
    assert evaluate_brain_tenant_gate("linas")["allow"] is True
    assert evaluate_brain_tenant_gate("other-shop")["allow"] is True
    assert evaluate_brain_tenant_gate("")["allow"] is False


@pytest.mark.asyncio
async def test_dm_uses_brain_without_enable_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    # Missing inbound ids → fail closed from Brain, not engine_removed from a flag.
    out = await run_customer_reply_v2_dm(tenant_id="linas", message="hi", conversation_id="", message_id="")
    assert out.metadata.get("customer_engine") == "brain" or out.reason != "engine_removed"
