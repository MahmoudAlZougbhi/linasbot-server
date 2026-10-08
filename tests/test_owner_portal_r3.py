"""Round-3 owner portal fixes: Q&A match, ghosts, usage, Voyage, and archive."""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.brain.model_pricing import compute_cost_from_usage
from services.brain.search.store import StoreHit, StoreQueryResult, reset_memory_store
from services.owner_portal.protected_text import translate_kept
from services.owner_portal.turn_usage import priced_usage

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def _no_session():
    yield None


def test_orphan_qa_vectors_do_not_win_or_split_the_margin(monkeypatch) -> None:
    from services.owner_portal import owner_qa

    reset_memory_store()
    owner_qa._REINDEXED = True
    groups = [
        {
            "id": "qa-live",
            "variants": [{"language": "en", "question": "what is the cobalt-ember refund code?", "answer": "7461"}],
        }
    ]
    monkeypatch.setattr(owner_qa, "list_qa", lambda: groups)
    monkeypatch.setattr(owner_qa, "_session", _no_session)
    monkeypatch.setattr(owner_qa, "embed_one", lambda _text, *, query=False: [1.0, 0.0])

    def _found(_session, **_kwargs):
        return StoreQueryResult(
            outcome="found",
            items=[
                StoreHit("a", "t", "owner_qa", "orphan:en", "", "gone", 0.99),
                StoreHit("b", "t", "owner_qa", "qa-live:en", "", "live", 0.80),
                StoreHit("c", "t", "owner_qa", "qa-live:ar", "", "live-ar", 0.79),
            ],
        )

    monkeypatch.setattr("services.brain.search.store.query_similar", _found)
    hit = owner_qa.match_owner_qa("Could you tell me the refund code for cobalt ember?", "en")
    assert hit is not None
    assert hit["qa_id"] == "qa-live"
    assert hit["answer"] == "7461"
    assert owner_qa.match_owner_qa("What is the silver-otter refund code?", "en") is None

    def _weak(_session, **_kwargs):
        return StoreQueryResult(
            outcome="found",
            items=[StoreHit("b", "t", "owner_qa", "qa-live:en", "", "live", 0.40)],
        )

    monkeypatch.setattr("services.brain.search.store.query_similar", _weak)
    assert owner_qa.match_owner_qa("clinic opening hours on Friday?", "en") is None


def test_no_prefix_matches_the_stored_core_form(monkeypatch) -> None:
    from services.owner_portal import owner_qa

    owner_qa._REINDEXED = True
    monkeypatch.setattr(
        owner_qa,
        "list_qa",
        lambda: [
            {
                "id": "qa-live",
                "variants": [
                    {
                        "language": "en",
                        "question": "QA-CURSOR what is the cobalt-ember refund code?",
                        "answer": "7461",
                    }
                ],
            }
        ],
    )
    hit = owner_qa.match_owner_qa("what is the cobalt-ember refund code?", "en")
    assert hit is not None
    assert hit["hit"] == "exact"
    assert hit["answer"] == "7461"


@pytest.mark.asyncio
async def test_arabic_translation_retries_once_and_keeps_tokens() -> None:
    calls = {"n": 0}

    async def fake(text: str, attempt: int) -> str:
        calls["n"] += 1
        if attempt == 1:
            return "ما هو رمز الاسترداد"
        return text.replace("⟦T1⟧", "⟦T1⟧") + " بالعربية"

    question = "QA-CURSOR what is the cobalt-ember refund code?"
    rendered, attempts = await translate_kept(question, target="ar", translate=fake)
    assert attempts == 2
    assert calls["n"] == 2
    assert "QA-CURSOR" in rendered and "cobalt-ember" in rendered
    assert any("\u0600" <= char <= "\u06ff" for char in rendered)
    assert rendered != question


def test_deleted_knowledge_stops_answering(monkeypatch) -> None:
    from services.brain.providers.spaces import ENTITY_DOCUMENT
    from services.brain.search.store import _MEMORY
    from services.owner_portal import owner_kb_store

    reset_memory_store()
    entries = [{"id": "kb1", "title": "Cobalt heron", "body": "kept for 19 hours", "updated_at": ""}]
    monkeypatch.setattr(owner_kb_store, "list_entries", lambda: list(entries))
    monkeypatch.setattr(owner_kb_store, "embed_one", lambda text, **_kwargs: [1.0, 0.0] if text else None)
    monkeypatch.setattr(owner_kb_store, "_session", _no_session)
    assert owner_kb_store._reindex("kb1", "Cobalt heron", "kept for 19 hours") is True
    assert owner_kb_store.search_kb("cobalt heron")
    entries.clear()
    owner_kb_store.delete_entry("kb1")
    assert owner_kb_store.search_kb("cobalt heron") == []
    assert all(row.get("parent_id") != "kb1" for bucket in _MEMORY.values() for row in bucket)

    _MEMORY.setdefault("linas-owner-copilot", []).append(
        {
            "id": "owner-kb-ghost",
            "tenant_id": "linas-owner-copilot",
            "space_id": ENTITY_DOCUMENT.space_id,
            "source_family": "owner_kb",
            "source_id": "ghost",
            "parent_id": "ghost",
            "search_text": "63 days",
            "title": "ghost",
            "visible": True,
            "embedding": [1.0, 0.0],
        }
    )
    assert owner_kb_store.search_kb("63 days") == []


def test_usage_comes_from_the_provider_or_is_flagged() -> None:
    priced = priced_usage(
        qa_hit=False,
        usage={"prompt_tokens": 1234, "completion_tokens": 56},
        reply="hello",
        message="question",
        model="gpt-5.1",
    )
    assert priced["tokens_in"] == 1234
    assert priced["tokens_out"] == 56
    assert priced["usage_estimated"] is False
    assert priced["cost_usd"] == compute_cost_from_usage("gpt-5.1", 1234, 56)["cost_usd"]
    assert priced["cost_usd"] > 0
    estimated = priced_usage(qa_hit=False, usage=None, reply="hello!!", message="question", model="gpt-5.1")
    assert estimated["usage_estimated"] is True
    assert estimated["tokens_out"] == max(1, len("hello!!") // 4)
    qa = priced_usage(
        qa_hit=True, usage={"prompt_tokens": 9, "completion_tokens": 9}, reply="x", message="y", model="m"
    )
    assert qa == {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "usage_estimated": False}


@pytest.mark.asyncio
async def test_owner_embed_backoff_does_not_block_the_loop(monkeypatch) -> None:
    from services.owner_portal.owner_embed import embed_one_async

    def slow(_text: str, *, query: bool = False, feature: str = "owner_embed") -> list[float]:
        time.sleep(0.25)
        return [0.1]

    monkeypatch.setattr("services.owner_portal.owner_embed.embed_one", slow)
    started = asyncio.get_running_loop().time()
    task = asyncio.create_task(embed_one_async("hello", query=True))
    await asyncio.sleep(0)
    assert asyncio.get_running_loop().time() - started < 0.1
    assert await task == [0.1]


def test_unchanged_qa_text_is_not_embedded_again(monkeypatch) -> None:
    from services.owner_portal import owner_qa
    from services.owner_portal.embed_jobs import reset_jobs_for_tests

    reset_memory_store()
    reset_jobs_for_tests()
    owner_qa._REINDEXED = False
    rows = [{"language": "en", "question": "hello there", "answer": "world"}]
    calls = {"n": 0}

    def _embed(_text: str, *, query: bool = False) -> list[float]:
        calls["n"] += 1
        return [1.0, 0.0]

    monkeypatch.setattr(owner_qa, "embed_one", _embed)
    monkeypatch.setattr(owner_qa, "list_qa", lambda: [{"id": "q1", "variants": rows}])
    monkeypatch.setattr(owner_qa, "_session", _no_session)
    assert owner_qa._index("q1", rows) is True
    assert calls["n"] == 1
    owner_qa._REINDEXED = False
    owner_qa.ensure_reindexed()
    assert calls["n"] == 1


def test_failed_embed_is_queued_and_drained(monkeypatch) -> None:
    from services.brain.search.store import _MEMORY
    from services.owner_portal import owner_qa
    from services.owner_portal.embed_jobs import drain_embed_jobs, reset_jobs_for_tests

    reset_memory_store()
    reset_jobs_for_tests()
    rows = [{"language": "en", "question": "queue me", "answer": "later"}]
    calls = {"n": 0}

    def _embed(_text: str, *, query: bool = False) -> list[float] | None:
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return [0.4, 0.2]

    monkeypatch.setattr(owner_qa, "embed_one", _embed)
    monkeypatch.setattr(owner_qa, "_session", _no_session)
    assert owner_qa._index("qa-job", rows) is False
    assert drain_embed_jobs() == 1
    stored = [row for bucket in _MEMORY.values() for row in bucket if row.get("parent_id") == "qa-job"]
    assert stored


def test_provider_error_keeps_the_active_index(monkeypatch) -> None:
    from services.brain.search.index_lifecycle import get_lifecycle, mark_active, mark_failed, reset_lifecycle_for_tests
    from services.brain.search.store import activate_pointer, tenant_pointer_ready

    reset_lifecycle_for_tests()
    reset_memory_store()
    monkeypatch.setattr("services.brain.search.index_lifecycle._save_sql", lambda _row: None)
    monkeypatch.setattr("services.brain.search.index_lifecycle._load_sql", lambda _tenant: None)
    mark_active("shop", active_version="v1", content_revision="v1")
    activate_pointer(None, tenant_id="shop", space_id="entity", source_family="knowledge", version="v1", count=3)
    failed = mark_failed("shop", revision="v2", reason="provider_error")
    assert failed["status"] == "FAILED"
    assert failed["active_version"] == "v1"
    assert get_lifecycle("shop")["status"] == "FAILED"
    assert tenant_pointer_ready(None, "shop") is True


def test_build_time_reads_the_release_source(monkeypatch, tmp_path: Path) -> None:
    from services.owner_portal.release_version import build_time

    monkeypatch.delenv("LINAS_BUILD_TIME", raising=False)
    monkeypatch.setenv("LINAS_BUILD_TIME_FILE", str(tmp_path / "missing"))
    assert build_time() == ""
    stamp = "2026-10-08T14:05:00Z"
    monkeypatch.setenv("LINAS_BUILD_TIME", stamp)
    assert build_time() == stamp


def test_voyage_429_is_counted(monkeypatch) -> None:
    from services.owner_portal.voyage_metrics import note_voyage, recent_count, reset_metrics_for_tests

    reset_metrics_for_tests()
    monkeypatch.setattr("db.session.whatsapp_session", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("no db")))
    note_voyage("owner_qa", 429, retry_after="2")
    note_voyage("owner_qa", 200)
    assert recent_count(feature="owner_qa", seconds=300) == 1


def test_archive_hides_junk_and_blocks_reuse(monkeypatch) -> None:
    from services.owner_portal.tenant_archive import (
        KEEP_TENANTS,
        archive_tenants,
        archived_tenant_ids,
        reset_archive_for_tests,
        reuse_blocked,
    )

    reset_archive_for_tests()
    monkeypatch.setattr(
        "db.session.whatsapp_session",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("no db")),
    )
    archived = archive_tenants(
        [
            {"tenant_id": "probe-clinic", "email": "a@p.tld"},
            {"tenant_id": "linas", "email": "owner@linas.ai"},
        ]
    )
    assert archived == ["probe-clinic"]
    assert "linas" not in archived_tenant_ids()
    assert "probe-clinic" in archived_tenant_ids()
    assert reuse_blocked(tenant_id="probe-clinic")
    assert reuse_blocked(tenant_id="new-shop", email="a@p.tld")
    assert reuse_blocked(tenant_id="linas", email="a@p.tld") is False
    assert "apple-account" in KEEP_TENANTS


def test_confirm_archives_the_matching_candidate_list(capsys, monkeypatch) -> None:
    import json

    from scripts.owner_portal_junk_tenants import main as junk_main
    from services.owner_portal.tenant_archive import archived_tenant_ids, reset_archive_for_tests

    reset_archive_for_tests()
    monkeypatch.setattr(
        "db.session.whatsapp_session",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("no db")),
    )
    rows = [
        {
            "tenant_id": "probe-clinic",
            "business_name": "Probe",
            "email": "a@p.tld",
            "messages_used": 0,
            "credits_used": 0,
            "historical_credit_remaining": 0,
            "payments": 0,
            "published_brain": False,
        }
    ]
    code = junk_main(["--confirm", "--tenant-ids", "probe-clinic", "--rows-json", json.dumps(rows)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["archived"] == ["probe-clinic"]
    assert "probe-clinic" in archived_tenant_ids()


def test_message_flows_load_events_once_per_tenant(monkeypatch) -> None:
    from services.brain.turn_inspector import list_message_flows

    calls = {"n": 0}

    class _Item:
        def __init__(self, operation_id: str) -> None:
            self.tenant_id = "linas"
            self.operation_id = operation_id
            self.outbox_id = operation_id
            self.extra = {"channel": "instagram_dm"}
            self.state = "sent"
            self.updated_at = "2026-10-08T08:22:32Z"
            self.envelope = {"messages": [{"text": "ok"}]}

    def _events(*, tenant_id: str):
        calls["n"] += 1
        return []

    monkeypatch.setattr("services.brain.turn_inspector.list_recent", lambda **_kwargs: [_Item("a"), _Item("b")])
    monkeypatch.setattr("services.brain.turn_inspector.list_events", _events)
    rows = list_message_flows(tenant_id="linas", limit=10)
    assert calls["n"] == 1
    assert [row["operation_id"] for row in rows] == ["a", "b"]


def test_api_names_the_serving_host() -> None:
    from modules.security_headers import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/api/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).get("/api/ping")
    served = response.headers.get("x-served-by") or ""
    assert served
    assert " " not in served
    assert not any(char.isdigit() and served.count(".") >= 3 for char in served)


def test_migration_purges_orphan_vectors_and_adds_the_parent_index() -> None:
    text = (ROOT / "alembic" / "versions" / "20261008_portal_r3.py").read_text(encoding="utf-8")
    assert "ix_search_docs_family_parent" in text
    assert "owner_copilot_kb_entries" in text
    assert "owner_copilot_qa" in text
    assert "owner_portal_orphan_vector_backup" in text
    assert "LIKE" not in text


@pytest.mark.asyncio
async def test_brain_reuses_one_qa_match(monkeypatch) -> None:
    from services.owner_copilot.brain import iter_owner_turn_v2_events

    calls = {"n": 0}

    def _match(_question: str, _language: str) -> dict[str, object]:
        calls["n"] += 1
        return {"qa_id": "q", "answer": "7461", "score": 1.0, "hit": "exact"}

    monkeypatch.setattr("services.owner_copilot.brain.owner_copilot_v2_enabled", lambda: True)
    monkeypatch.setattr("services.owner_portal.owner_qa.match_owner_qa", _match)
    events = []
    async for event in iter_owner_turn_v2_events(
        tenant_id="linas",
        user_id="owner",
        role="platform_owner",
        conversation_id="c1",
        user_text="what is the code?",
    ):
        events.append(event)
        break
    assert calls["n"] == 1
    reused = []
    async for event in iter_owner_turn_v2_events(
        tenant_id="linas",
        user_id="owner",
        role="platform_owner",
        conversation_id="c1",
        user_text="what is the code?",
        qa_match={"qa_id": "q", "answer": "7461", "score": 1.0, "hit": "exact"},
        qa_match_ready=True,
    ):
        reused.append(event)
        break
    assert calls["n"] == 1
    assert events and reused
