"""LOC split: qa_database_service and local_qa_service match mixins under 500 lines."""

from __future__ import annotations

from pathlib import Path

from services.local_qa_service import LocalQAService
from services.local_qa_service import get_qa_response as local_get
from services.local_qa_service_match import LocalQAServiceMatchMixin
from services.qa_database_service import QADatabaseService
from services.qa_database_service import get_qa_response as db_get
from services.qa_database_service_match import QADatabaseServiceMatchMixin


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_qa_service_modules_under_500_lines() -> None:
    assert _line_count("services/qa_database_service.py") < 500
    assert _line_count("services/qa_database_service_match.py") < 500
    assert _line_count("services/local_qa_service.py") < 500
    assert _line_count("services/local_qa_service_match.py") < 500


def test_qa_services_preserve_public_api_via_mixin() -> None:
    assert issubclass(QADatabaseService, QADatabaseServiceMatchMixin)
    assert issubclass(LocalQAService, LocalQAServiceMatchMixin)
    assert callable(db_get)
    assert callable(local_get)
    for name in ("find_match", "normalize_text", "get_statistics", "get_categories"):
        assert callable(getattr(QADatabaseService, name))
        assert callable(getattr(LocalQAService, name))
