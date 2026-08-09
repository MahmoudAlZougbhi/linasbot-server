"""FAQ single-entry: CM FAQ is the only writer; legacy Bot Training writes are blocked."""

from __future__ import annotations

import pytest

from services.cm.constants import cm_faq_canonical

pytestmark = pytest.mark.usefixtures("enable_faq_plan")


def test_cm_faq_canonical_defaults_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CM_FAQ_CANONICAL", raising=False)
    assert cm_faq_canonical() is True


def test_cm_faq_canonical_can_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CM_FAQ_CANONICAL", "false")
    assert cm_faq_canonical() is False


@pytest.mark.asyncio
async def test_legacy_local_qa_create_blocked_when_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CM_FAQ_CANONICAL", "true")
    from modules.local_qa_api import create_local_qa_pair

    result = await create_local_qa_pair({"question": "q", "answer": "a", "language": "en"})
    assert result["success"] is False
    assert result["error"] == "CM_FAQ_CANONICAL"
    assert result["redirect"] == "/content-managers/faq"


@pytest.mark.asyncio
async def test_legacy_qa_create_blocked_when_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CM_FAQ_CANONICAL", "true")
    from modules.qa_api import create_qa_pair

    result = await create_qa_pair({"question": "q", "answer": "a", "language": "en"})
    assert result["success"] is False
    assert result["error"] == "CM_FAQ_CANONICAL"
    assert result["redirect"] == "/content-managers/faq"


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
        "services.cm.faq_integration.language_detection_service.translate_training_pair",
        _fake_translate,
    )
    monkeypatch.setattr(
        "services.cm.faq_integration._translate_to_arabic_script",
        _fake_ar,
    )

    remote_calls: list[str] = []

    async def _forbidden_remote(**_kwargs):  # type: ignore[no-untyped-def]
        remote_calls.append("remote")
        raise AssertionError("remote QA must not be called")

    monkeypatch.setattr(
        "services.qa_database_service.qa_db_service.create_qa_pair",
        _forbidden_remote,
        raising=False,
    )

    from services.cm.faq_integration import create_faq_pair_from_livechat, list_cm_faq

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
    assert remote_calls == []
