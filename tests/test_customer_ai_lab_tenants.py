"""Owner Lab capture-only tenant gate includes Linas Laser."""

from __future__ import annotations

from services.cm.constants import DEFAULT_TENANT_ID
from services.customer_ai.test_lab import lab_turn_tenant_allowed


def test_lab_turn_allows_lab_and_linas() -> None:
    assert lab_turn_tenant_allowed("lab") is True
    assert lab_turn_tenant_allowed("lab_demo") is True
    assert lab_turn_tenant_allowed(DEFAULT_TENANT_ID) is True
    assert lab_turn_tenant_allowed("linas") is True
    assert lab_turn_tenant_allowed("other-shop") is False
    assert lab_turn_tenant_allowed("") is False
