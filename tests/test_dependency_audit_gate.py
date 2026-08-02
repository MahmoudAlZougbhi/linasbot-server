"""Fail-closed static contract for the npm production audit gate."""

from pathlib import Path


def test_npm_audit_gate_rejects_network_and_incomplete_reports() -> None:
    source = Path("scripts/npm_audit_gate.mjs").read_text(encoding="utf-8")

    assert "report?.error" in source
    assert "report?.auditReportVersion !== 2" in source
    assert "!completeSeverityCounts" in source
    assert "refusing to pass" in source
