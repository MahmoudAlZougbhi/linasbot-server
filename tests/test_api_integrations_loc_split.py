"""Deleted api_integrations loc-split files stay gone."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_api_integrations_files_are_gone() -> None:
    assert not (ROOT / "services/api_integrations.py").exists()
    assert not (ROOT / "services/api_integrations_http.py").exists()
