"""LOC split: local_qa helpers under 500 lines; HTTP CRUD is gone."""

from __future__ import annotations

from pathlib import Path

from modules.local_qa_api_helpers import (
    build_qa_entry,
    create_local_qa_pair_internal,
    read_qa_pairs,
)


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_local_qa_api_modules_under_500_lines() -> None:
    assert _line_count("modules/local_qa_api.py") < 500
    assert _line_count("modules/local_qa_api_helpers.py") < 500
    assert not Path("modules/local_qa_api_faq.py").exists()


def test_local_qa_api_preserves_public_helpers() -> None:
    from modules import local_qa_api

    assert local_qa_api.read_qa_pairs is read_qa_pairs
    assert local_qa_api.create_local_qa_pair_internal is create_local_qa_pair_internal
    assert local_qa_api.build_qa_entry is build_qa_entry
    assert callable(local_qa_api.create_local_qa_pair)
