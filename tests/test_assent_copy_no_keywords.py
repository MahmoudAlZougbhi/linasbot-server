"""S4: propose errors must not list ok / موافق / yes as assent magic."""

from __future__ import annotations

from pathlib import Path


def test_propose_error_points_to_approve_bar_not_keywords() -> None:
    src = Path("services/owner_copilot/tools_write.py").read_text(encoding="utf-8")
    assert "ok / موافق" not in src
    assert "short assent" not in src
    assert "Approve bar" in src or "confirm_tool" in src
