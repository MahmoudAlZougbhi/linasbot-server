"""Legacy local QA HTTP helpers are gone; CM FAQ is the only writer."""

from __future__ import annotations

from pathlib import Path


def test_legacy_local_qa_modules_are_gone() -> None:
    assert not Path("modules/local_qa_api.py").exists()
    assert not Path("modules/local_qa_api_helpers.py").exists()
    assert not Path("modules/local_qa_api_faq.py").exists()
    assert not Path("services/faq/local_qa_service.py").exists()
