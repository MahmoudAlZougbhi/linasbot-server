"""API readiness must not fail solely because OpenAI is temporarily unset."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_openai_is_reported_but_does_not_fail_api_readiness() -> None:
    src = (ROOT / "modules" / "dashboard_api_health.py").read_text(encoding="utf-8")
    assert '"openai_api_key"' in src or "openai_api_key" in src
    assert "readiness_dependency" in src
    assert "if not openai_ok:\n        overall_ok = False" not in src
