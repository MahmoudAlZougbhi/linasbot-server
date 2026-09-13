"""WAVE 1 freeze: the destructive archive delete-all script stays gone."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_archive_delete_all_conversations_script_removed() -> None:
    assert not (ROOT / "archive").exists()
    assert not (ROOT / "archive" / "scripts" / "delete_all_conversations.py").exists()
    assert not (ROOT / "scripts" / "delete_all_conversations.py").exists()
