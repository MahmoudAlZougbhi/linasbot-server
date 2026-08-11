"""Proactive CM quality_pass findings for Owner Copilot reviews."""

from __future__ import annotations

import pytest

from services.cm.quality_audit import run_cm_quality_audit
from services.cm.schemas import default_section_payload
from services.cm.storage import put_draft


@pytest.fixture()
def tenant(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    from pathlib import Path

    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", Path(tmp_path))
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return "tenant_quality_audit"


def test_quality_audit_finds_duplicates_and_suspicious(tenant: str) -> None:
    put_draft(
        "faq",
        payload={
            "items": [
                {
                    "qa_group_id": "g1",
                    "variants": [
                        {"language": "en", "question": "What are your hours?", "answer": "TODO placeholder hours"},
                    ],
                    "status": "active",
                },
                {
                    "qa_group_id": "g2",
                    "variants": [
                        {"language": "en", "question": "What are your hours?", "answer": "We open at 9"},
                    ],
                    "status": "active",
                },
            ],
            "notes": None,
        },
        if_match=None,
        updated_by="test",
        tenant_id=tenant,
    )
    put_draft(
        "knowledge",
        payload={
            "items": [
                {"id": "k1", "title": "Laser aftercare", "body": "TBD"},
                {"id": "k2", "title": "Laser aftercare", "body": "Apply cream twice daily for a week."},
            ],
            "notes": None,
        },
        if_match=None,
        updated_by="test",
        tenant_id=tenant,
    )

    audit = run_cm_quality_audit(tenant)
    assert audit["quality_pass"] is True
    cats = {f["category"] for f in audit["findings"]}
    assert "duplicate" in cats
    assert "suspicious" in cats or "unclear" in cats
    assert "missing" in cats or "weak_incomplete" in cats
    assert "duplicates" in " ".join(audit["checklist"])
    assert "halwse" in audit["report_style"] or "halwse" in " ".join(audit["checklist"])


def test_quality_audit_improve_services_without_prices(tenant: str) -> None:
    put_draft(
        "services",
        payload={
            "items": [{"id": "laser", "labels": {"en": "Laser", "ar": "ليزر", "fr": "", "franco": ""}}],
            "notes": None,
        },
        if_match=None,
        updated_by="test",
        tenant_id=tenant,
    )
    # prices left at missing/default
    audit = run_cm_quality_audit(tenant)
    improve = [f for f in audit["findings"] if f.get("category") == "improve" and f.get("section") == "prices"]
    assert improve, audit["findings"]


def test_guide_includes_quality_checklist() -> None:
    from services.cm.section_guide import guide_for_section

    g = guide_for_section("faq")
    assert g is not None
    assert "duplicates" in " ".join(g.get("quality_checklist") or [])
