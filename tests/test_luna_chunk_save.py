"""Save-time chunks for large owner text; edit replaces old chunks and embeddings."""

from __future__ import annotations

import pytest

from services.ai_setup.search_metadata.errors import MetadataPreparationError
from services.ai_setup.search_metadata.generate import (
    SearchMetadata,
    reset_metadata_generator,
    set_metadata_generator,
)
from services.ai_setup.storage import put_draft
from services.brain.compiler.chunk_apply import last_chunk_apply_stats
from services.brain.compiler.chunk_store import chunk_path, chunk_texts, read_chunks
from services.brain.compiler.luna_chunker import reset_chunk_generator, set_chunk_generator
from services.brain.retrieve.cards import TitleCard, cards_from_sections
from services.brain.search.contextual_index import build_contextual_rows
from services.brain.search.index_job import document_rows

LONG_NOTE = (
    "After laser hair removal avoid heat swimming perfume and direct sun for two days. "
    "Use the clinic cream twice daily and do not wax or pluck between sessions. "
    "Call the branch if redness lasts more than forty eight hours after treatment. "
    "Bring the same notes to every visit so the assistant can quote aftercare exactly."
)
assert len(LONG_NOTE) >= 280


def _meta() -> None:
    set_metadata_generator(
        lambda _req: SearchMetadata(
            title="English Search Title",
            description="Contains the grounded item content for routing.",
        )
    )


def _chunks_from_request(calls: list[dict]):
    def _gen(request: dict) -> list[dict[str, str]]:
        calls.append(dict(request))
        text = str(request.get("content") or "").replace("lasre", "laser").replace("removel", "removal")
        mid = max(len(text) // 2, 1)
        return [
            {"heading": "Part 1", "text": text[:mid].strip()},
            {"heading": "Part 2", "text": text[mid:].strip() or text[:mid].strip()},
        ]

    set_chunk_generator(_gen)


def setup_function() -> None:
    reset_metadata_generator()
    reset_chunk_generator()
    _meta()


def teardown_function() -> None:
    reset_metadata_generator()
    reset_chunk_generator()


def test_knowledge_save_stores_luna_chunks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    calls: list[dict] = []
    _chunks_from_request(calls)
    env = put_draft(
        "knowledge",
        payload={"items": [{"id": "k1", "title": "Aftercare", "body": LONG_NOTE, "status": "active"}]},
        if_match="*",
        tenant_id="t-luna-k",
        allow_create=True,
    )
    texts = chunk_texts("t-luna-k", "knowledge", "k1")
    assert len(texts) == 2
    assert "Part 1" in texts[0]
    assert last_chunk_apply_stats()["generated_ids"] == ["k1"]
    assert len(calls) == 1
    assert env.payload["items"][0]["body"] == LONG_NOTE


def test_knowledge_edit_replaces_old_chunks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    calls: list[dict] = []
    _chunks_from_request(calls)
    first = put_draft(
        "knowledge",
        payload={"items": [{"id": "k1", "title": "Aftercare", "body": LONG_NOTE, "status": "active"}]},
        if_match="*",
        tenant_id="t-luna-edit",
        allow_create=True,
    )
    old = read_chunks("t-luna-edit", "knowledge", "k1")
    put_draft(
        "knowledge",
        payload={
            "items": [
                {
                    "id": "k1",
                    "title": "Aftercare",
                    "body": LONG_NOTE + " New: no sauna after the lasre removel session.",
                    "status": "active",
                }
            ]
        },
        if_match=first.etag,
        tenant_id="t-luna-edit",
    )
    new = read_chunks("t-luna-edit", "knowledge", "k1")
    assert new is not None and old is not None
    assert new["fingerprint"] != old["fingerprint"]
    blob = " ".join(chunk_texts("t-luna-edit", "knowledge", "k1"))
    assert "laser" in blob
    assert "lasre" not in blob
    assert last_chunk_apply_stats()["generated_ids"] == ["k1"]
    assert len(calls) == 2


def test_unchanged_knowledge_does_not_rechunk(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    calls: list[dict] = []
    _chunks_from_request(calls)
    payload = {
        "items": [
            {"id": "k1", "title": "A", "body": LONG_NOTE, "status": "active"},
            {"id": "k2", "title": "B", "body": "Short file body.", "status": "active"},
        ]
    }
    first = put_draft("knowledge", payload=payload, if_match="*", tenant_id="t-luna-keep", allow_create=True)
    put_draft(
        "knowledge",
        payload={
            "items": [
                {"id": "k1", "title": "A", "body": LONG_NOTE + " Extra shaving note for evening.", "status": "active"},
                {"id": "k2", "title": "B", "body": "Short file body.", "status": "active"},
            ]
        },
        if_match=first.etag,
        tenant_id="t-luna-keep",
    )
    stats = last_chunk_apply_stats()
    assert stats["generated_ids"] == ["k1"]
    assert "k2" in stats["copied_ids"]
    assert [c["item_id"] for c in calls] == ["k1", "k2", "k1"]


def test_deleted_knowledge_removes_sidecar(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    _chunks_from_request([])
    first = put_draft(
        "knowledge",
        payload={
            "items": [
                {"id": "gone", "title": "Old", "body": LONG_NOTE, "status": "active"},
                {"id": "keep", "title": "Keep", "body": LONG_NOTE, "status": "active"},
            ]
        },
        if_match="*",
        tenant_id="t-luna-del",
        allow_create=True,
    )
    assert chunk_path("t-luna-del", "knowledge", "gone").exists()
    put_draft(
        "knowledge",
        payload={"items": [{"id": "keep", "title": "Keep", "body": LONG_NOTE, "status": "active"}]},
        if_match=first.etag,
        tenant_id="t-luna-del",
    )
    assert not chunk_path("t-luna-del", "knowledge", "gone").exists()
    assert chunk_path("t-luna-del", "knowledge", "keep").exists()
    assert last_chunk_apply_stats()["removed_ids"] == ["gone"]


def test_clock_only_hours_are_not_chunked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    calls: list[dict] = []
    _chunks_from_request(calls)
    put_draft(
        "opening_hours",
        payload={
            "items": [
                {
                    "id": "h1",
                    "title": "Week",
                    "monday": {"closed": False, "open": "09:00", "close": "18:00"},
                }
            ]
        },
        if_match="*",
        tenant_id="t-luna-h",
        allow_create=True,
    )
    assert read_chunks("t-luna-h", "opening_hours", "h1") is None
    assert calls == []


def test_short_title_knowledge_is_not_chunked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    calls: list[dict] = []
    _chunks_from_request(calls)
    put_draft(
        "knowledge",
        payload={"items": [{"id": "t1", "title": "Aftercare", "body": "", "status": "active"}]},
        if_match="*",
        tenant_id="t-luna-title",
        allow_create=True,
    )
    assert read_chunks("t-luna-title", "knowledge", "t1") is None
    assert calls == []


def test_branch_long_notes_are_chunked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    calls: list[dict] = []
    _chunks_from_request(calls)
    put_draft(
        "branches",
        payload={"items": [{"id": "b1", "labels": {"en": "Hamra"}, "notes": LONG_NOTE, "available": True}]},
        if_match="*",
        tenant_id="t-luna-b",
        allow_create=True,
    )
    assert chunk_texts("t-luna-b", "branches", "b1")
    assert calls and calls[0]["item_id"] == "b1"


def test_service_title_without_notes_is_not_chunked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    calls: list[dict] = []
    _chunks_from_request(calls)
    put_draft(
        "prices",
        payload={"catalog": [{"id": "s1", "labels": {"en": "Laser"}, "description": "", "active": True}]},
        if_match="*",
        tenant_id="t-luna-s",
        allow_create=True,
    )
    assert read_chunks("t-luna-s", "prices", "s1") is None
    assert calls == []


def test_service_long_description_is_chunked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    _chunks_from_request([])
    put_draft(
        "prices",
        payload={"catalog": [{"id": "s1", "labels": {"en": "Laser"}, "description": LONG_NOTE, "active": True}]},
        if_match="*",
        tenant_id="t-luna-sd",
        allow_create=True,
    )
    assert chunk_texts("t-luna-sd", "prices", "s1")


def test_request_short_name_not_chunked_long_notes_are(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    calls: list[dict] = []
    _chunks_from_request(calls)
    put_draft(
        "requests_appointments",
        payload={
            "module_enabled": True,
            "enabled_types": ["APPOINTMENT"],
            "rules": [{"id": "r1", "type": "APPOINTMENT", "name": "Booking", "notes": "Phone only.", "enabled": True}],
        },
        if_match="*",
        tenant_id="t-luna-r",
        allow_create=True,
    )
    assert read_chunks("t-luna-r", "requests_appointments", "r1") is None
    put_draft(
        "requests_appointments",
        payload={
            "module_enabled": True,
            "enabled_types": ["APPOINTMENT"],
            "rules": [{"id": "r1", "type": "APPOINTMENT", "name": "Booking", "notes": LONG_NOTE, "enabled": True}],
        },
        if_match="*",
        tenant_id="t-luna-r2",
        allow_create=True,
    )
    assert chunk_texts("t-luna-r2", "requests_appointments", "r1")
    assert any(c["section"] == "requests_appointments" for c in calls)


def test_index_rows_use_stored_luna_chunks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    _chunks_from_request([])
    env = put_draft(
        "knowledge",
        payload={"items": [{"id": "k1", "title": "Aftercare", "body": LONG_NOTE, "status": "active"}]},
        if_match="*",
        tenant_id="t-luna-ix",
        allow_create=True,
    )
    cards = cards_from_sections({"knowledge": env.payload}, tenant_id="t-luna-ix")
    assert cards[0].chunks
    rows = document_rows(cards, tenant_id="t-luna-ix", version="v1")
    assert len(rows) == len(cards[0].chunks)
    assert all(row["chunk_id"] for row in rows)
    assert {row["chunk_id"] for row in rows} == {
        f"{cards[0].item_id}:c{index}" for index in range(1, len(cards[0].chunks) + 1)
    }


def test_knowledge_without_luna_sidecar_is_single_row_not_mechanical_split() -> None:
    card = TitleCard(
        item_id="knowledge:k1",
        source_family="knowledge",
        title="Aftercare",
        search_text="aftercare " + LONG_NOTE,
        body="# Part A\n" + LONG_NOTE + "\n# Part B\n" + LONG_NOTE,
    )
    rows = document_rows([card], tenant_id="t-no-luna", version="v1")
    assert len(rows) == 1
    assert rows[0]["chunk_id"] == ""
    ctx_rows, _groups, _parents = build_contextual_rows([card], tenant_id="t-no-luna", version="v1")
    assert len(ctx_rows) == 1


def test_luna_and_legacy_chunk_ids_do_not_mix() -> None:
    card = TitleCard(
        item_id="knowledge:k1",
        source_family="knowledge",
        title="Aftercare",
        search_text="aftercare",
        body="# Heading One\nlegacy split bait one.\n# Heading Two\nlegacy split bait two.",
        chunks=("Luna piece one.", "Luna piece two."),
    )
    rows = document_rows([card], tenant_id="shop", version="v1")
    ids = [row["chunk_id"] for row in rows]
    assert ids == ["knowledge:k1:c1", "knowledge:k1:c2"]
    assert len(ids) == len(set(ids))
    blob = " ".join(row["search_text"] for row in rows)
    assert "legacy split bait" not in blob


def test_rewrite_drops_leftover_chunk_ids_for_same_item() -> None:
    from services.brain.search.store import _MEMORY, reset_memory_store, write_documents

    reset_memory_store()
    old = TitleCard(
        item_id="knowledge:k1",
        source_family="knowledge",
        title="Aftercare",
        search_text="aftercare",
        chunks=("one", "two", "three"),
    )
    new = TitleCard(
        item_id="knowledge:k1",
        source_family="knowledge",
        title="Aftercare",
        search_text="aftercare",
        chunks=("one", "two"),
    )
    old_rows = document_rows([old], tenant_id="t-drop", version="v1")
    write_documents(None, old_rows, [[0.1, 0.0] for _ in old_rows])
    new_rows = document_rows([new], tenant_id="t-drop", version="v1")
    write_documents(None, new_rows, [[0.2, 0.0] for _ in new_rows])
    leftover = [
        item
        for item in _MEMORY.get("t-drop", [])
        if str(item.get("source_id") or "") == "k1" and str(item.get("index_version") or "") == "v1"
    ]
    assert len(leftover) == 2
    assert {str(item.get("chunk_id") or "") for item in leftover} == {"knowledge:k1:c1", "knowledge:k1:c2"}


def test_contextual_index_prefers_luna_chunks() -> None:
    card = TitleCard(
        item_id="knowledge:k1",
        source_family="knowledge",
        title="Aftercare",
        search_text="aftercare",
        body="mechanical body that should not be sliced",
        chunks=("Luna chunk one about cream.", "Luna chunk two about sun."),
    )
    rows, groups, _parents = build_contextual_rows([card], tenant_id="shop", version="v1")
    assert len(rows) == 2
    blob = " ".join(row["search_text"] for row in rows)
    assert "Luna chunk one" in blob
    assert "mechanical body" not in blob
    assert groups and "Luna chunk one" in groups[0][0]


def test_long_greeting_and_ai_basics_are_chunked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    _chunks_from_request([])
    put_draft(
        "dynamic_messages",
        payload={"items": [{"id": "g1", "name": "Welcome", "en": LONG_NOTE, "ar": LONG_NOTE, "enabled": True}]},
        if_match="*",
        tenant_id="t-luna-g",
        allow_create=True,
    )
    assert chunk_texts("t-luna-g", "dynamic_messages", "g1")
    put_draft(
        "ai_basics",
        payload={"assistant_name": "Luna", "identity_summary": LONG_NOTE, "greeting_behavior": LONG_NOTE},
        if_match="*",
        tenant_id="t-luna-ai",
        allow_create=True,
    )
    from services.brain.compiler.prose import SECTION_ITEM_ID

    assert chunk_texts("t-luna-ai", "ai_basics", SECTION_ITEM_ID)


def test_luna_chunk_fail_closed_on_save(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")

    def _boom(_request: dict):
        raise RuntimeError("luna down")

    monkeypatch.setattr("services.brain.compiler.luna_chunker._llm_enabled", lambda: True)
    monkeypatch.setattr("services.brain.compiler.luna_chunker._luna_chunks", _boom)
    with pytest.raises(MetadataPreparationError):
        put_draft(
            "knowledge",
            payload={"items": [{"id": "k1", "title": "A", "body": LONG_NOTE, "status": "active"}]},
            if_match="*",
            tenant_id="t-luna-fail",
            allow_create=True,
        )
