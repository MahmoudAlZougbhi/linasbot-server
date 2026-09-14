"""Visual retrieval is separate from sending an authorized asset by ID."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualDecision:
    needed: bool
    reason: str


def visual_path_for_resource(*, has_authorized_id: bool) -> str:
    if has_authorized_id:
        return "resource_by_id"
    return "not_needed"


def visual_retrieval_decision(
    *,
    has_authorized_asset_id: bool,
    image_analysis_enabled: bool = False,
    requires_visual_reading: bool = False,
) -> VisualDecision:
    if has_authorized_asset_id:
        return VisualDecision(False, "resource_by_id")
    if not requires_visual_reading:
        return VisualDecision(False, "not_needed")
    if not image_analysis_enabled:
        return VisualDecision(False, "disabled")
    return VisualDecision(False, "disabled")
