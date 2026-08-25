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
    # Optional Comments + Requests & Appointments defaults count as filled
    # (no owner content required; Requests stays capture-inactive until enabled/published).
    optional_done = 2  # comments + requests_appointments
    assert summary["complete"] == optional_done
    assert summary["incomplete"] == summary["total"] - optional_done
    assert summary["percent"] == int(round((optional_done / summary["total"]) * 100))
    assert "ai_basics" in summary["missing_sections"]
    assert "comments" in summary["complete_sections"]
    assert "requests_appointments" in summary["complete_sections"]


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


def test_progress_branches_complete_with_legacy_opening_hours(tenant_root: Path) -> None:
    del tenant_root
    tid = "progress-hours-tenant"
    put_draft(
        "branches",
        payload={
            "items": [
                {
                    "id": "main",
                    "labels": {"en": "Main", "ar": "", "fr": "", "franco": ""},
                    "address": "Beirut",
                    "weekly_schedule": {},
                }
            ],
            "timezone": "Asia/Beirut",
            "specific_off_rules": [],
        },
        if_match="*",
        updated_by="test",
        tenant_id=tid,
        allow_create=True,
    )
    put_draft(
        "opening_hours",
        payload={
            "items": [
                {
                    "id": "main",
                    "title": "Main",
                    "monday": {"open": "09:00", "close": "18:00", "closed": False},
                }
            ]
        },
        if_match="*",
        updated_by="test",
        tenant_id=tid,
        allow_create=True,
    )
    rows = list_section_fill_status(tid, create_missing=False)
    by_sec = {r["section"]: r for r in rows}
    assert by_sec["branches"]["fill"] == "filled"
    assert by_sec["branches"]["status"] == "complete"
    assert by_sec["opening_hours"]["fill"] == "filled"


def test_progress_branches_complete_with_legacy_hours_summary(tenant_root: Path) -> None:
    del tenant_root
    tid = "progress-legacy-hours"
    put_draft(
        "branches",
        payload={
            "items": [
                {
                    "id": "main",
                    "labels": {"en": "Main", "ar": "", "fr": "", "franco": ""},
                    "address": "Beirut",
                    "hours": {"summary": "Mon-Fri 9-6"},
                    "weekly_schedule": {},
                }
            ],
            "timezone": "Asia/Beirut",
            "specific_off_rules": [],
        },
        if_match="*",
        updated_by="test",
        tenant_id=tid,
        allow_create=True,
    )
    rows = list_section_fill_status(tid, create_missing=False)
    branches = next(r for r in rows if r["section"] == "branches")
    assert branches["fill"] == "filled"
    assert branches["status"] == "complete"


def test_progress_branches_complete_when_times_without_enabled_flag(tenant_root: Path) -> None:
    del tenant_root
    tid = "progress-coalesce-hours"
    put_draft(
        "branches",
        payload={
            "items": [
                {
                    "id": "main",
                    "labels": {"en": "Main", "ar": "", "fr": "", "franco": ""},
                    "address": "Beirut",
                    "weekly_schedule": {
                        "monday": {"enabled": False, "open": "09:00", "close": "18:00", "off_day": False},
                    },
                }
            ],
            "timezone": "Asia/Beirut",
            "specific_off_rules": [],
        },
        if_match="*",
        updated_by="test",
        tenant_id=tid,
        allow_create=True,
    )
    rows = list_section_fill_status(tid, create_missing=False)
    branches = next(r for r in rows if r["section"] == "branches")
    assert branches["fill"] == "filled"
    assert branches["status"] == "complete"
