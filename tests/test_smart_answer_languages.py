"""Smart Answer language settings (P1)."""

from __future__ import annotations

from services.cm.faq_integration_helpers import FAQ_SECTION
from services.cm.schemas import FaqSection
from services.cm.smart_answer_languages import (
    DEFAULT_SMART_ANSWER_LANGUAGES,
    normalize_smart_answer_languages,
    save_smart_answer_languages,
)
from services.cm.storage import get_draft


def test_default_smart_answer_languages() -> None:
    langs = normalize_smart_answer_languages(None)
    assert langs == list(DEFAULT_SMART_ANSWER_LANGUAGES)


def test_normalize_dedupes_and_filters() -> None:
    langs = normalize_smart_answer_languages(["en", "EN", "es", "bogus", "ar", "ur"])
    assert langs == ["en", "es", "ar", "ur"]


def test_catalog_includes_urdu() -> None:
    from services.cm.iso639_languages import iso639_catalog

    ids = {item["id"] for item in iso639_catalog()}
    assert "ur" in ids
    assert len(ids) >= 180


def test_faq_section_schema_has_smart_answer_languages() -> None:
    section = FaqSection.model_validate({"items": [], "smart_answer_languages": ["en", "ar"]})
    assert section.smart_answer_languages == ["en", "ar"]


def test_faq_record_complete_for_selected_languages() -> None:
    from services.cm.schemas import FaqRecord, FaqVariant

    record = FaqRecord(
        qa_group_id="qa_test",
        variants=[
            FaqVariant(language="en", question="Q", answer="A"),
            FaqVariant(language="ar", question="س", answer="ج"),
        ],
    )
    assert record.is_complete_for_languages(["en", "ar"])
    assert not record.is_complete_for_languages(["en", "ar", "fr"])


def test_save_smart_answer_languages_persists_in_draft(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("storage.persistent_storage.get_data_root", lambda: str(tmp_path))
    from services.cm.storage import ensure_defaults

    ensure_defaults(tenant_id="linas")
    result = save_smart_answer_languages(
        tenant_id="linas",
        languages=["en", "es"],
        updated_by="test",
    )
    assert result["smart_answer_languages"] == ["en", "es"]
    env = get_draft(FAQ_SECTION, tenant_id="linas", create_default=True)
    section = FaqSection.model_validate(env.payload)
    assert section.smart_answer_languages == ["en", "es"]
