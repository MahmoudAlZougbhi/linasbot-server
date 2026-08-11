"""LOC split: owner_ai CM content/upsert under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services import owner_ai_tools_cm_content as cm
from services.owner_ai_tools_cm_upsert import tool_propose_cm_article_upsert as upsert_propose


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_owner_ai_cm_content_modules_under_500_lines() -> None:
    assert _line_count("services/owner_ai_tools_cm_content.py") < 500
    assert _line_count("services/owner_ai_tools_cm_upsert.py") < 500


def test_owner_ai_cm_content_preserves_public_api() -> None:
    assert cm.tool_propose_cm_article_upsert is upsert_propose
    assert callable(cm.tool_list_cm_articles)
    assert callable(cm.tool_read_cm_faq)
    assert callable(cm.tool_propose_cm_faq_upsert)
    assert callable(cm.compact_read_cm_draft)
