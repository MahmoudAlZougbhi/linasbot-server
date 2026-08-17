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


def test_normalize_explicit_list_does_not_reinject_defaults() -> None:
    assert normalize_smart_answer_languages(["en", "zh"]) == ["en", "zh"]
    assert normalize_smart_answer_languages([]) == []
    assert normalize_smart_answer_languages(["bogus"]) == []


def test_mirror_preserves_smart_answer_languages(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("storage.persistent_storage.get_data_root", lambda: str(tmp_path))
    from services.cm.faq_integration_helpers import _mirror_faq_record_into_draft
    from services.cm.schemas import FaqRecord, FaqVariant
    from services.cm.storage import ensure_defaults, get_draft

    tenant_id = "mirror_lang_preserve"
    ensure_defaults(tenant_id=tenant_id)
    save_smart_answer_languages(tenant_id=tenant_id, languages=["en", "zh"], updated_by="test")
    record = FaqRecord(
        qa_group_id="qa_mirror",
        variants=[FaqVariant(language="en", question="Q", answer="A")],
        status="draft",
    )
    _mirror_faq_record_into_draft(record, tenant_id=tenant_id, updated_by="test")
    env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    section = FaqSection.model_validate(env.payload)
    assert section.smart_answer_languages == ["en", "zh"]
    assert section.items[-1].qa_group_id == "qa_mirror"


def test_catalog_includes_urdu() -> None:
    from services.cm.iso639_languages import iso639_catalog

    ids = {item["id"] for item in iso639_catalog()}
    assert "ur" in ids
    assert len(ids) >= 180


def test_purge_smart_answer_language_deletes_variants_and_runtime_rows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("storage.persistent_storage.get_data_root", lambda: str(tmp_path))
    from services.cm.faq_integration_ops import purge_smart_answer_language_data
    from services.cm.schemas import FaqRecord, FaqVariant
    from services.cm.storage import ensure_defaults, get_draft, put_draft
    from services.local_qa_service import local_qa_service

    tenant_id = "purge_lang_test"
    ensure_defaults(tenant_id=tenant_id)
    env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    section = FaqSection.model_validate(env.payload)
    record = FaqRecord(
        qa_group_id="qa_purge",
        variants=[
            FaqVariant(language="en", question="Q", answer="A"),
            FaqVariant(language="ur", question="سوال", answer="جواب"),
        ],
        status="draft",
    )
    put_draft(
        FAQ_SECTION,
        payload=FaqSection(
            items=[record],
            notes=section.notes,
            smart_answer_languages=["en", "ur", "ar"],
        ).model_dump(mode="json"),
        if_match=env.etag,
        tenant_id=tenant_id,
        updated_by="test",
    )
    local_qa_service.qa_pairs = [
        {"tenant_id": tenant_id, "language": "ur", "question": "سوال", "answer": "جواب", "qa_group_id": "qa_purge"},
        {"tenant_id": tenant_id, "language": "en", "question": "Q", "answer": "A", "qa_group_id": "qa_purge"},
    ]

    result = purge_smart_answer_language_data(language="ur", tenant_id=tenant_id, updated_by="test")
    assert result["variants_removed"] == 1
    assert result["deleted_runtime_rows"] == 1
    assert "ur" not in result["smart_answer_languages"]

    env2 = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    section2 = FaqSection.model_validate(env2.payload)
    assert section2.smart_answer_languages == ["en", "ar"]
    langs = {v.language for v in section2.items[0].variants}
    assert langs == {"en"}
    assert all(pair.get("language") != "ur" for pair in local_qa_service.qa_pairs)


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
