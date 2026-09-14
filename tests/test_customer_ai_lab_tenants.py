"""Owner Lab capture-only tenant gate is lab tenants only."""

from __future__ import annotations

from services.brain.test_lab import lab_turn_tenant_allowed


def test_lab_turn_allows_lab_prefix_only() -> None:
    assert lab_turn_tenant_allowed("lab") is True
    assert lab_turn_tenant_allowed("lab_demo") is True
    assert lab_turn_tenant_allowed("linas") is False
    assert lab_turn_tenant_allowed("other-shop") is False
    assert lab_turn_tenant_allowed("") is False
