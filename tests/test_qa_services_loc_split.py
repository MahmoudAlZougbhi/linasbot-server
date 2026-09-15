"""LOC split: local_qa_service match mixins under 500 lines."""

from __future__ import annotations

from pathlib import Path

from services.faq.local_qa_service import LocalQAService
from services.faq.local_qa_service import get_qa_response as local_get
from services.faq.local_qa_service_match import LocalQAServiceMatchMixin


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_qa_service_modules_under_500_lines() -> None:
    assert _line_count("services/faq/local_qa_service.py") < 500
    assert _line_count("services/faq/local_qa_service_match.py") < 500


def test_qa_services_preserve_public_api_via_mixin() -> None:
    assert issubclass(LocalQAService, LocalQAServiceMatchMixin)
    assert callable(local_get)
    for name in ("find_match", "normalize_text", "get_statistics", "get_categories"):
        assert callable(getattr(LocalQAService, name))
