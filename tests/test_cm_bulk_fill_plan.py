"""Bulk CM fill plan storage + status transitions."""

from __future__ import annotations

from services.cm import bulk_fill as bf


def test_store_and_peek_bulk_sections(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "services.cm.bulk_fill.tenant_cm_root",
        lambda tenant_id: tmp_path / tenant_id,
    )
    plan = bf.store_bulk_sections(
        tenant_id="t1",
        user_id="u1",
        source="text",
        sections=[
            {
                "section": "ai_basics",
                "patch": {
                    "clinic_name": "Test Clinic",
                    "assistant_name": "Lina",
                },
                "note": "identity",
            },
            {"section": "not_a_section", "patch": {"x": 1}},
        ],
        missing_notes=["opening_hours missing"],
    )
    assert plan["status"] == "active"
    assert len(plan["queue"]) == 1
    assert "not_a_section" in plan["rejected"]
    nxt = bf.peek_next_pending(plan)
    assert nxt is not None
    assert nxt["section"] == "ai_basics"
    plan = bf.mark_section_status(plan, "ai_basics", "applied")
    assert bf.peek_next_pending(plan) is None
    assert plan["status"] == "complete"
