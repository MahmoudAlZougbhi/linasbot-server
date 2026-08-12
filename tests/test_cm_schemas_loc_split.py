"""LOC split: services.cm.schemas re-exports content models under 500 lines."""

from __future__ import annotations

from pathlib import Path

from services.cm.schemas import (
    AiBasics,
    AiLimitsSection,
    BranchRecord,
    CommentsSection,
    LocalizedLabels,
    default_section_payload,
    initial_restricted_policy,
)


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_cm_schema_modules_under_500_lines() -> None:
    assert _line_count("services/cm/schemas.py") < 500
    assert _line_count("services/cm/schemas_content.py") < 500
    assert _line_count("services/cm/schemas_requests.py") < 500


def test_public_schemas_import_still_exposes_content_and_runtime() -> None:
    from services.cm.schemas import RequestsAppointmentsSection

    assert LocalizedLabels(en="Hello").en == "Hello"
    assert AiBasics().assistant_name == ""
    assert CommentsSection().default_action == "reply_comment"
    assert AiLimitsSection().image_per_day == 20
    branch = BranchRecord(id="b1", street="Main", building="2")
    assert branch.composed_address() == "Main, 2"
    payload = default_section_payload("ai_basics")
    assert "clinic_name" in payload
    policy = initial_restricted_policy()
    assert policy.topics
    assert all(t.active is False for t in policy.topics)
    ra = RequestsAppointmentsSection.model_validate(default_section_payload("requests_appointments"))
    assert ra.module_enabled is False
    assert ra.enabled_types == []
