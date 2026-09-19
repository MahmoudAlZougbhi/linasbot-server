"""LOC split: canonical FAQ services stay under 500 lines; local QA is gone."""

from __future__ import annotations

from pathlib import Path

from services.ai_setup.faq_invalidation import invalidate_faq_for_cm_patch
from services.brain.faq_exact import find_published_exact_faq, published_faq_entry


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_canonical_faq_modules_under_500_lines() -> None:
    assert _line_count("services/brain/faq_exact.py") < 500
    assert _line_count("services/brain/faq_semantic.py") < 500
    assert _line_count("services/ai_setup/faq_invalidation.py") < 500
    assert not Path("services/faq/local_qa_service.py").exists()
    assert not Path("services/faq/local_qa_service_match.py").exists()


def test_canonical_faq_public_api() -> None:
    assert callable(find_published_exact_faq)
    assert callable(published_faq_entry)
    assert callable(invalidate_faq_for_cm_patch)
