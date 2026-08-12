"""LOC split: Content Management control-plane plan sections under 500 lines."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


PARTS = [
    "docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md",
    "docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_overview.md",
    "docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_architecture.md",
    "docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_runtime.md",
    "docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_phases.md",
]


def test_cm_control_plane_plan_parts_under_500_lines() -> None:
    for rel in PARTS:
        assert _line_count(rel) < 500, rel


def test_cm_control_plane_plan_index_links_sections() -> None:
    index = Path("docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN.md").read_text(encoding="utf-8")
    assert "CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_overview.md" in index
    assert "CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_architecture.md" in index
    assert "CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_runtime.md" in index
    assert "CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_phases.md" in index
    overview = Path("docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_overview.md").read_text(encoding="utf-8")
    assert "Revision delta" in overview
    phases = Path("docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_phases.md").read_text(encoding="utf-8")
    assert "Phased implementation plan" in phases
