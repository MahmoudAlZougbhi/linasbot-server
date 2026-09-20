"""Portal runtime_limits: code defaults + Live published overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.runtime_limits.defaults import DEFAULT_LIMITS
from services.runtime_limits.loader import load_runtime_limits
from tests.cm_test_helpers import publish_pointer_content


@pytest.fixture()
def tenant_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return "limits-tenant"


def test_missing_section_uses_code_defaults(tenant_root: str) -> None:
    limits = load_runtime_limits(tenant_root)
    assert limits == DEFAULT_LIMITS
    assert limits.owner_history_messages == 100
    assert limits.owner_message_max_chars == 0
    assert limits.customer_history_messages == 50
    assert limits.customer_message_max_chars == 600
    assert limits.product_search_cap == 24
    assert limits.catalog_evidence_cap == 18
    assert limits.max_retrieval_rounds == 3
    assert limits.max_agent_steps == 6
    assert limits.max_tool_calls == 8


def test_live_published_overrides_without_restart(tenant_root: str) -> None:
    publish_pointer_content(
        tenant_root,
        {
            "runtime_limits": {
                "owner_history_messages": 80,
                "owner_message_max_chars": 0,
                "customer_history_messages": 40,
                "customer_message_max_chars": 600,
                "product_search_cap": 12,
                "catalog_evidence_cap": 10,
                "max_retrieval_rounds": 2,
                "max_agent_steps": 5,
                "max_tool_calls": 7,
            }
        },
    )
    limits = load_runtime_limits(tenant_root)
    assert limits.owner_history_messages == 80
    assert limits.customer_history_messages == 40
    assert limits.product_search_cap == 12
    assert limits.max_retrieval_rounds == 2


def test_out_of_range_values_clamp(tenant_root: str) -> None:
    publish_pointer_content(
        tenant_root,
        {"runtime_limits": {"owner_history_messages": 9999, "max_retrieval_rounds": 0}},
    )
    limits = load_runtime_limits(tenant_root)
    assert limits.owner_history_messages == 500
    assert limits.max_retrieval_rounds == 1
