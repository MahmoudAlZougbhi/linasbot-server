"""FAQ single-entry: CM FAQ is the only writer; legacy Bot Training writes are blocked."""

from __future__ import annotations

import pytest

from services.ai_setup.constants import cm_faq_canonical

pytestmark = pytest.mark.usefixtures("enable_faq_plan")


def test_cm_faq_canonical_defaults_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CM_FAQ_CANONICAL", raising=False)
    assert cm_faq_canonical() is True


def test_cm_faq_canonical_can_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CM_FAQ_CANONICAL", "false")
    assert cm_faq_canonical() is False


def test_legacy_local_qa_runtime_removed_when_canonical() -> None:
    from pathlib import Path

    assert not Path("modules/local_qa_api.py").exists()
    assert not Path("services/faq/local_qa_service.py").exists()


@pytest.mark.asyncio
async def test_livechat_like_still_writes_cm_faq_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live Chat Like → Save to FAQ must keep writing via CM FAQ (not dual-write)."""
    monkeypatch.setenv("CM_FAQ_CANONICAL", "true")

    async def _fake_translate(**kwargs):  # type: ignore[no-untyped-def]
        q = kwargs.get("question") or ""
        a = kwargs.get("answer") or ""
        langs = kwargs.get("target_languages") or []
        return {
            "success": True,
            "translations": {
                lang: {
                    "question": q if lang == (kwargs.get("source_language") or "ar") else f"{lang}:{q}",
                    "answer": a if lang in ("ar", "franco") else f"{lang}:{a}",
                }
                for lang in langs
            },
        }

    async def _fake_ar(text: str, _src: str) -> str:
        return "السعر عشرين دولار."

    monkeypatch.setattr(
        "services.ai_setup.faq_integration.language_detection_service.translate_training_pair",
        _fake_translate,
    )
    monkeypatch.setattr(
        "services.ai_setup.faq_integration._translate_to_arabic_script",
        _fake_ar,
    )
    from services.ai_setup.faq_integration import create_faq_pair_from_livechat, list_cm_faq

    result = await create_faq_pair_from_livechat(
        question="shu se3r el laser?",
        answer="ashreen dolar",
        language="franco",
        tenant_id="tenant_faq_single_entry",
        updated_by="test_operator",
    )
    assert result["success"] is True
    assert result["count_created"] == 4
    groups = list_cm_faq(tenant_id="tenant_faq_single_entry")
    assert any(g["qa_group_id"] == result["qa_group_id"] for g in groups)
