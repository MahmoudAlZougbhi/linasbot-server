"""Deleted BOC intent pipeline stays gone."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_intent_pipeline_files_are_gone() -> None:
    assert not (ROOT / "services/booking").exists()
