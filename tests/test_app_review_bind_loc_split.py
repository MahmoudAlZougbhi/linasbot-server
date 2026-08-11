"""LOC split: app_review_bind helpers under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services.whatsapp_cloud import app_review_bind
from services.whatsapp_cloud.app_review_bind_helpers import AppReviewBindError as HelperError


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_app_review_bind_modules_under_500_lines() -> None:
    assert _line_count("services/whatsapp_cloud/app_review_bind.py") < 500
    assert _line_count("services/whatsapp_cloud/app_review_bind_helpers.py") < 500


def test_app_review_bind_preserves_public_api() -> None:
    assert app_review_bind.AppReviewBindError is HelperError
    assert app_review_bind.APP_REVIEW_SOURCE == "meta_app_review_test"
    assert callable(app_review_bind.status_app_review_bind)
    assert callable(app_review_bind.bind_app_review_test_number)
    assert callable(app_review_bind.unbind_app_review_test_number)
