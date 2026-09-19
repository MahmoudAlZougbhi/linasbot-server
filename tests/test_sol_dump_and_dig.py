"""Dump split → batch proposals + comment-rule ask + tenant dig."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from services.owner_copilot.tools_cm_bulk import tool_ingest_business_dump
from services.owner_copilot.tools_comment_rules import tool_propose_comment_rule
from services.owner_copilot.tools_dig import _duplicate_rows, tool_dig_tenant_cm


@pytest.fixture()
def tenant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", Path(tmp_path))
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return "tenant_sol_dump"


@pytest.mark.asyncio
async def test_ingest_proposes_multiple_sections(tenant: str, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _extract(**_k: Any) -> dict[str, Any]:
        return {
            "sections": [
                {"section": "ai_basics", "patch": {"clinic_name": "Nour"}, "note": "ok"},
                {"section": "style", "patch": {"tone": "warm"}, "note": "ok"},
            ],
            "missing_notes": ["What are Saturday hours?"],
        }

    monkeypatch.setattr("services.ai_setup.bulk_fill.extract_sections_from_dump", _extract)

    async def _propose(**kwargs: Any) -> Any:
        from services.owner_copilot.tools_base import ToolResult

        sec = str(kwargs.get("section") or "")
        return ToolResult(
            ok=True,
            name="propose_cm_patch",
            data={
                "proposal_id": f"p-{sec}",
                "confirmation_token": f"approve_cm_patch:p-{sec}",
                "preview": {
                    "section": sec,
                    "change_kind": "edit",
                    "before": "",
                    "after": "x",
                    "item_title": sec,
                },
                "requires_confirmation": True,
            },
            requires_confirmation=True,
            confirmation_token=f"approve_cm_patch:p-{sec}",
        )

    monkeypatch.setattr("services.owner_copilot.tools_write.tool_propose_cm_patch", _propose)
    result = await tool_ingest_business_dump(
        tenant_id=tenant,
        role="admin",
        user_id="u1",
        text="We are a clinic in Beirut. Warm replies. Open weekdays 9-5.",
    )
    assert result.ok is True
    proposals = result.data.get("proposals") or []
    assert len(proposals) == 2
    assert "Saturday" in " ".join(str(x) for x in (result.data.get("bulk_plan") or {}).get("missing_notes") or [])


@pytest.mark.asyncio
async def test_comment_rule_asks_before_card() -> None:
    result = await tool_propose_comment_rule(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        args={"name": "Post rule"},
    )
    assert result.ok is True
    assert result.data.get("needs_clarification") is True
    assert result.data.get("missing_fields")


def test_duplicate_scan() -> None:
    dupes = _duplicate_rows(
        [
            {"id": "a", "title": "Hours"},
            {"id": "b", "title": "hours"},
        ],
        section="knowledge",
    )
    assert dupes


@pytest.mark.asyncio
async def test_dig_tenant_cm_readonly(tenant: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.ai_setup.progress.progress_summary",
        lambda *_a, **_k: {
            "percent": 10,
            "missing_sections": ["faq"],
            "weak_sections": [],
            "filled_sections": ["languages"],
        },
    )
    monkeypatch.setattr("services.ai_setup.quality_audit.run_cm_quality_audit", lambda *_a, **_k: {"findings": []})

    async def _recent(**_k: Any) -> Any:
        from services.owner_copilot.tools_base import ToolResult

        return ToolResult(ok=True, name="get_recent_customer_interactions", data={"items": []})

    monkeypatch.setattr(
        "services.owner_copilot.tools_diagnosis.tool_get_recent_customer_interactions",
        _recent,
    )
    result = await tool_dig_tenant_cm(tenant_id=tenant, role="admin", user_id="u1")
    assert result.ok is True
    assert "duplicates" in result.data
    assert "channels" in result.data
