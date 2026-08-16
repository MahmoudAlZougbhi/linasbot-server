"""Live-cert contract: Real vs BLOCKED labels, never mock-as-live."""

from __future__ import annotations

from pathlib import Path

from _live_cert.bootstrap import looks_real_openai_key

ROOT = Path(__file__).resolve().parents[1]


def test_fake_keys_are_not_real() -> None:
    assert looks_real_openai_key("sk-test") is False
    assert looks_real_openai_key("sk-test-ci-not-real") is False
    assert looks_real_openai_key("") is False
    assert looks_real_openai_key("not-a-key") is False


def test_live_runner_does_not_use_fixtures() -> None:
    text = (ROOT / "_live_cert/run_live.py").read_text(encoding="utf-8")
    assert "fixture_answer" not in text
    assert "scripted_retrieval" not in text
    assert "sk-test" not in text


def test_whatsapp_stays_off_in_live_bootstrap() -> None:
    text = (ROOT / "_live_cert/bootstrap.py").read_text(encoding="utf-8")
    assert "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY" in text
    assert '"false"' in text


def test_owner_ui_comments_keep_resource_modal() -> None:
    comments = (ROOT / "mobile/linas-ai/src/features/cm/comments/CommentsScreen.tsx").read_text(encoding="utf-8")
    assert "ResourceMetaModal" in comments
