"""CM fill progress — complete vs default/missing drafts."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.cm.progress import list_section_fill_status, progress_summary
from services.cm.schemas import default_section_payload
from services.cm.storage import put_draft


@pytest.fixture()
def tenant_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return tmp_path


def test_progress_marks_default_incomplete(tenant_root: Path) -> None:
    del tenant_root
    summary = progress_summary("progress-tenant", create_missing=False)
    # Optional Comments policy defaults count as filled (no owner content required).
    optional_done = 1  # comments
    assert summary["complete"] == optional_done
    assert summary["incomplete"] == summary["total"] - optional_done
    assert summary["percent"] == int(round((optional_done / summary["total"]) * 100))
    assert "ai_basics" in summary["missing_sections"]
    assert "comments" in summary["complete_sections"]


def test_progress_marks_filled_complete(tenant_root: Path) -> None:
    del tenant_root
    base = default_section_payload("ai_basics")
    put_draft(
        "ai_basics",
        payload={**base, "clinic_name": "Iron Peak", "business_purpose": "Training gym"},
        if_match="*",
        updated_by="test",
        tenant_id="progress-tenant",
        allow_create=True,
    )
    rows = list_section_fill_status("progress-tenant", create_missing=False)
    by_sec = {r["section"]: r["status"] for r in rows}
    assert by_sec["ai_basics"] == "complete"
    assert by_sec["services"] == "incomplete"
    summary = progress_summary("progress-tenant", create_missing=False)
    assert summary["complete"] >= 1
    assert "ai_basics" in summary["complete_sections"]
    assert "ai_basics" not in summary["missing_sections"]
