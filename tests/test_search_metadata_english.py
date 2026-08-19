"""Internal metadata must be English, not merely Latin-script."""

from __future__ import annotations

import pytest

from services.search_metadata.english import english_only_or_empty, looks_like_english
from services.search_metadata.errors import METADATA_PREPARATION_MESSAGE, MetadataPreparationError
from services.search_metadata.generate import (
    SearchMetadata,
    generate_search_metadata,
    last_generate_stats,
    reset_metadata_generator,
    set_metadata_generator,
)


def setup_function() -> None:
    reset_metadata_generator()


def teardown_function() -> None:
    reset_metadata_generator()


def test_looks_like_english_accepts_english() -> None:
    assert looks_like_english("Beirut Hamra Branch")
    assert looks_like_english("Contains Beirut Hamra location, opening hours, notes, and map link.")


def test_latin_non_english_is_rejected() -> None:
    samples = {
        "fr": "Horaires d'ouverture de Beyrouth",
        "es": "Horario de apertura de la sucursal",
        "de": "Öffnungszeiten der Filiale Beirut",
        "it": "Orari di apertura della filiale",
        "ar": "أسعار الجلسات",
        "zh": "营业时间说明",
        "hi": "सत्र की कीमतें",
    }
    for _lang, text in samples.items():
        assert looks_like_english(text) is False, text
        assert english_only_or_empty(text) == "", text


def test_generator_french_spanish_german_italian_not_saved() -> None:
    set_metadata_generator(
        lambda req: SearchMetadata(
            title=str(req.get("title") or ""),
            description=str(req.get("description") or ""),
        )
    )
    cases = [
        ("Horaires d'ouverture", "Contient les heures d'ouverture"),
        ("Horario de apertura", "Contiene el horario de la sucursal"),
        ("Öffnungszeiten Beirut", "Enthält die Öffnungszeiten der Filiale"),
        ("Orari di apertura", "Contiene gli orari della filiale"),
    ]
    for title, description in cases:
        with pytest.raises(MetadataPreparationError):
            generate_search_metadata(
                {
                    "kind": "cm",
                    "title": title,
                    "description": description,
                    "content": "ignored",
                    "include_keywords": False,
                }
            )


def test_non_english_llm_output_retries_then_saves_english(monkeypatch) -> None:
    calls: list[bool] = []

    def fake_luna(request: dict) -> SearchMetadata:
        calls.append(bool(request.get("english_retry")))
        if request.get("english_retry"):
            return SearchMetadata(
                title="Beirut Opening Hours",
                description="Weekly open and close times for the Beirut branch.",
            )
        return SearchMetadata(
            title="Horaires d'ouverture",
            description="Contient les heures d'ouverture",
        )

    monkeypatch.setenv("LINAS_SEARCH_METADATA_LLM", "1")
    monkeypatch.setenv("ENVIRONMENT", "development")
    reset_metadata_generator()
    monkeypatch.setattr("services.search_metadata.generate._llm_enabled", lambda: True)
    monkeypatch.setattr("services.search_metadata.generate._generate_with_luna", fake_luna)
    from services.search_metadata.generate import last_generate_stats

    meta = generate_search_metadata(
        {
            "kind": "cm",
            "section": "opening_hours",
            "original_title": "ساعات",
            "content": "monday 09:00-18:00 sunday closed",
            "include_keywords": False,
        }
    )
    stats = last_generate_stats()
    assert calls == [False, True]
    assert stats["llm_calls"] == 2
    assert stats["retries"] == 1
    assert meta.title == "Beirut Opening Hours"
    assert looks_like_english(meta.title)
    assert looks_like_english(meta.description)


def test_retry_still_non_english_fails_save(monkeypatch) -> None:
    def fake_luna(_request: dict) -> SearchMetadata:
        return SearchMetadata(title="Horaires d'ouverture", description="Contient les heures")

    reset_metadata_generator()
    monkeypatch.setattr("services.search_metadata.generate._llm_enabled", lambda: True)
    monkeypatch.setattr("services.search_metadata.generate._generate_with_luna", fake_luna)

    with pytest.raises(MetadataPreparationError) as exc:
        generate_search_metadata(
            {
                "kind": "cm",
                "content": "hours",
                "include_keywords": False,
            }
        )
    stats = last_generate_stats()
    assert stats["retries"] == 1
    assert stats["saved_empty"] is True
    assert "luna" not in str(exc.value).lower()
    assert "openai" not in str(exc.value).lower()
    assert "key" not in METADATA_PREPARATION_MESSAGE.lower()


def test_empty_title_or_description_is_not_ready() -> None:
    set_metadata_generator(lambda _req: SearchMetadata(title="", description="Contains a short English summary."))
    with pytest.raises(MetadataPreparationError):
        generate_search_metadata({"kind": "cm", "content": "body", "include_keywords": False})
    set_metadata_generator(lambda _req: SearchMetadata(title="English Search Title", description=""))
    with pytest.raises(MetadataPreparationError):
        generate_search_metadata({"kind": "cm", "content": "body", "include_keywords": False})


def test_invented_digit_facts_are_rejected() -> None:
    set_metadata_generator(
        lambda _req: SearchMetadata(
            title="Session priced at 99 USD",
            description="Contains an invented price that is not in the file.",
        )
    )
    with pytest.raises(MetadataPreparationError):
        generate_search_metadata(
            {
                "kind": "cm",
                "original_title": "12b",
                "content": "Laser session notes without a listed price.",
                "include_keywords": False,
            }
        )
