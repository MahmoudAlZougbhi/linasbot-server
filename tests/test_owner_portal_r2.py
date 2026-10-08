"""Round-2 owner portal fixes: shared state, traces, and Q&A search."""

from __future__ import annotations

import os
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.brain.search.store import reset_memory_store
from services.owner_portal.franco import franco_pair, to_franco
from services.owner_portal.owner_qa import _index, match_owner_qa
from services.owner_portal.owner_traces import _is_secret_key, write_trace
from services.owner_portal.release_version import git_sha, short_sha
from services.owner_portal.shared_events import ensure_tables, insert_audit_event, list_audit_events
from services.team.tenant_identity import classify_tenant, is_junk_identity


def _sqlite_session(path):
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine)

    @contextmanager
    def _open(*, require: bool = False):
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _open


def test_usage_fields_are_not_redacted() -> None:
    assert _is_secret_key("tokens_in") is False
    assert _is_secret_key("tokens_out") is False
    assert _is_secret_key("api_key") is True


def test_write_trace_persists_tokens(tmp_path, monkeypatch) -> None:
    opener = _sqlite_session(tmp_path / "traces.sqlite")
    with opener() as session:
        session.execute(
            text(
                """
                CREATE TABLE owner_message_traces (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT, brain TEXT, channel TEXT, created_at TEXT,
                    has_error INTEGER, tokens_in INTEGER, tokens_out INTEGER,
                    cost_usd DOUBLE PRECISION, payload TEXT
                )
                """
            )
        )
    monkeypatch.setattr("db.session.whatsapp_session", opener)
    trace_id = write_trace(
        {
            "tenant_id": "linas",
            "brain": "owner_copilot",
            "channel": "brains_test",
            "user_message": "hello",
            "reply": "world",
            "model": "gpt-5.6-sol",
            "tokens_in": 12,
            "tokens_out": 4,
            "cost_usd": 0.02,
            "error": "",
        }
    )
    assert trace_id
    with opener() as session:
        row = session.execute(
            text("SELECT brain, tokens_in, tokens_out, has_error FROM owner_message_traces WHERE id = :id"),
            {"id": trace_id},
        ).one()
    assert row[0] == "owner_copilot"
    assert row[1] == 12
    assert row[2] == 4
    assert row[3] == 0


def test_brains_test_does_not_record_a_second_customer_trace(monkeypatch) -> None:
    from services.brain.customer_response_trace import persist_from_interaction_entry

    seen: list[dict] = []
    monkeypatch.setattr(
        "services.brain.customer_response_trace.customer_response_trace_store.persist",
        lambda _trace: {"trace_id": "t1"},
    )
    monkeypatch.setattr("services.owner_portal.owner_traces.record_trace", seen.append)
    persist_from_interaction_entry(
        {"channel": "brains_test", "tenant_id": "linas", "user_message": "hi", "bot_to_user": "yo", "model": "m"}
    )
    assert seen == []


def test_two_instances_share_audit(tmp_path, monkeypatch) -> None:
    opener = _sqlite_session(tmp_path / "shared.sqlite")
    monkeypatch.setattr("db.session.whatsapp_session", opener)
    from services.team.platform_owner_service import PlatformOwnerService

    left = PlatformOwnerService(root=tmp_path / "a")
    right = PlatformOwnerService(root=tmp_path / "b")
    left.log_action(actor_user_id="owner", action="brain_lab_copilot", tenant_id="linas", details={})
    listed = right.list_actions()
    assert listed[0]["action"] == "brain_lab_copilot"
    assert listed[0]["id"] == list_audit_events()[0]["id"]
    assert insert_audit_event({"id": "same", "action": "x", "created_at": 1.0}) is True


def test_deleted_chat_is_not_read_from_the_other_nodes_file(tmp_path, monkeypatch) -> None:
    from services.owner_copilot.chat_store import OwnerChatStore

    opener = _sqlite_session(tmp_path / "chat.sqlite")
    with opener() as session:
        ensure_tables(session)
        session.execute(
            text(
                """
                CREATE TABLE owner_copilot_conversations (
                    id TEXT PRIMARY KEY, tenant_id TEXT, user_id TEXT, title TEXT,
                    created_at DOUBLE PRECISION, updated_at DOUBLE PRECISION,
                    archived INTEGER, deleted INTEGER, payload TEXT
                )
                """
            )
        )
    monkeypatch.setattr("db.session.whatsapp_session", opener)
    writer = OwnerChatStore(root=tmp_path / "node-a")
    reader = OwnerChatStore(root=tmp_path / "node-b")
    conv = writer.create_conversation(tenant_id="platform", user_id="owner", title="QA-LINAS-R2")
    assert reader.get_conversation(tenant_id="platform", user_id="owner", conversation_id=conv.id)
    assert writer.soft_delete(tenant_id="platform", user_id="owner", conversation_id=conv.id) is True
    assert reader.get_conversation(tenant_id="platform", user_id="owner", conversation_id=conv.id) is None
    assert reader.list_conversations(tenant_id="platform", user_id="owner") == []


def test_semantic_qa_uses_the_vector_store(monkeypatch) -> None:
    import re

    reset_memory_store()
    variants = [
        {
            "language": "en",
            "question": "what is the amber-falcon refund code?",
            "answer": "The amber-falcon refund code is 5293.",
        },
        {
            "language": "ar",
            "question": "ما هو رمز الاسترداد الخاص بـ amber-falcon؟",
            "answer": "QA-LINAS-RETEST The amber-falcon refund code is 5293.",
        },
        {
            "language": "franco",
            "question": "shu howe code el refund taba3 amber-falcon?",
            "answer": "QA-LINAS-RETEST code el refund taba3 amber-falcon howe 5293.",
        },
    ]

    def _embed(text: str, *, query: bool = False) -> list[float]:
        vector = [0.0] * 32
        for token in re.findall(r"\w+", text.lower()):
            if token in {"what", "is", "the", "for", "could", "you", "tell", "me", "please"}:
                continue
            vector[hash(token) % 32] += 1.0
        return vector

    from contextlib import contextmanager as _cm

    @_cm
    def _empty():
        yield None

    monkeypatch.setattr("services.owner_portal.owner_qa.embed_one", _embed)
    monkeypatch.setattr("services.owner_portal.owner_qa._session", _empty)
    monkeypatch.setattr(
        "services.owner_portal.owner_qa.list_qa",
        lambda: [{"id": "qa1", "variants": variants}],
    )
    monkeypatch.setattr("services.owner_portal.owner_qa._REINDEXED", True)
    _index("qa1", variants)
    assert match_owner_qa("what is the amber-falcon refund code please?", "en")["hit"] == "semantic"
    assert match_owner_qa("what is the amber-falcon refund code?", "en")["hit"] == "exact"
    assert match_owner_qa("Could you tell me the refund code for amber falcon?", "en")["answer"].endswith("5293.")
    assert match_owner_qa("ما هو رمز الاسترداد الخاص بـ amber-falcon؟ لو سمحت", "ar")["hit"] == "semantic"
    assert match_owner_qa("shu howe code el refund taba3 amber-falcon?", "franco")["hit"] == "exact"
    assert match_owner_qa("What are the clinic opening hours on Friday?", "en") is None
    assert match_owner_qa("What is the purple-lantern support code?", "en") is None


@pytest.mark.asyncio
async def test_franco_keeps_names_and_is_not_the_letter_map(monkeypatch) -> None:
    question = "QA-LINAS-RETEST what is the amber-falcon refund code?"
    answer = "QA-LINAS-RETEST The amber-falcon refund code is 5293."

    async def _reply(_question: str, _answer: str) -> str:
        return (
            "QA-LINAS-RETEST shu howe code el refund taba3 amber-falcon?\n---\n"
            "QA-LINAS-RETEST code el refund taba3 amber-falcon howe 5293."
        )

    monkeypatch.setattr("services.owner_portal.franco._ask_franco", _reply)
    franco_question, franco_answer = await franco_pair(question, answer)
    assert "amber-falcon" in franco_question and "5293" in franco_answer
    assert franco_question != to_franco(question)
    assert "shu" in franco_question


def test_junk_filter_and_protected_tenants() -> None:
    assert is_junk_identity(tenant_id="probe-clinic", business_name="Probe", email="a@p.tld")
    assert is_junk_identity(tenant_id="script-x-script", business_name="x", email="a@b.com")
    assert is_junk_identity(tenant_id="linas", business_name="<script>", email="a@linas.ai") is False
    assert is_junk_identity(tenant_id="layla-salon", business_name="صالون ليلى", email="a@shop.com") is False
    assert (
        classify_tenant({"tenant_id": "probe-clinic", "messages_used": 4, "business_name": "Probe", "email": "a@p.tld"})
        == "protected"
    )
    assert classify_tenant({"tenant_id": "apple-account", "email": "a@privaterelay.appleid.com"}) == (
        "needs_owner_review"
    )
    assert classify_tenant({"tenant_id": "ok-clinic", "email": "a@p.tld"}) == "candidate"


def test_write_trace_logs_a_database_error(monkeypatch, caplog) -> None:
    import logging

    def _boom(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("db.session.whatsapp_session", _boom)
    with caplog.at_level(logging.ERROR):
        assert write_trace({"tenant_id": "linas", "brain": "owner_copilot", "user_message": "hi"}) == ""
    assert "owner message trace was not stored" in caplog.text


def test_file_only_chat_is_imported_once(tmp_path, monkeypatch) -> None:
    from services.owner_copilot.chat_store import OwnerChatStore
    from services.owner_copilot.owner_chat_pg import reset_local_import

    opener = _sqlite_session(tmp_path / "chat.sqlite")
    with opener() as session:
        session.execute(
            text(
                """
                CREATE TABLE owner_copilot_conversations (
                    id TEXT PRIMARY KEY, tenant_id TEXT, user_id TEXT, title TEXT,
                    created_at DOUBLE PRECISION, updated_at DOUBLE PRECISION,
                    archived INTEGER, deleted INTEGER, payload TEXT
                )
                """
            )
        )
    monkeypatch.setattr("db.session.whatsapp_session", opener)
    reset_local_import()
    writer = OwnerChatStore(root=tmp_path / "node-a")
    payload = {
        "id": "file-only",
        "tenant_id": "platform",
        "user_id": "owner",
        "title": "QA-LINAS-R2 file",
        "created_at": 1,
        "updated_at": 2,
        "deleted": False,
        "messages": [{"id": "m", "role": "user", "content": "hi", "created_at": 1}],
    }
    path = writer._tenant_dir("platform")
    path.mkdir(parents=True, exist_ok=True)
    (path / "file-only.json").write_text(__import__("json").dumps(payload), encoding="utf-8")
    reader = OwnerChatStore(root=tmp_path / "node-b")
    assert writer.list_conversations(tenant_id="platform", user_id="owner")[0]["id"] == "file-only"
    assert reader.get_conversation(tenant_id="platform", user_id="owner", conversation_id="file-only")
    assert writer.soft_delete(tenant_id="platform", user_id="owner", conversation_id="file-only") is True
    reset_local_import()
    assert reader.get_conversation(tenant_id="platform", user_id="owner", conversation_id="file-only") is None


def test_visibility_override_hides_and_unhides(tmp_path, monkeypatch) -> None:
    from services.owner_portal.owner_portal_service import _hide_tenant
    from services.owner_portal.tenant_visibility import set_hidden

    opener = _sqlite_session(tmp_path / "vis.sqlite")
    monkeypatch.setattr("db.session.whatsapp_session", opener)
    assert (
        _hide_tenant(
            tenant_id="layla-salon",
            business_name="Layla",
            email="a@shop.com",
            status="active",
        )
        is False
    )
    assert set_hidden("layla-salon", True) == "ok"
    assert _hide_tenant(tenant_id="layla-salon", business_name="Layla", email="a@shop.com", status="active") is True
    assert set_hidden("linas", True) == "protected"
    assert set_hidden("probe-clinic", False) == "ok"
    assert _hide_tenant(tenant_id="probe-clinic", business_name="Probe", email="a@p.tld", status="active") is False


def test_message_flows_add_lab_rows_without_dropping_outbox(monkeypatch) -> None:
    import asyncio

    monkeypatch.setattr("modules.platform_message_api.require_platform_owner", lambda _request: object())
    monkeypatch.setattr(
        "services.brain.turn_inspector.list_message_flows",
        lambda **_kwargs: [{"operation_id": "out-1", "updated_at": "2020-01-01T00:00:00Z", "channel": "whatsapp"}],
    )
    monkeypatch.setattr(
        "services.owner_portal.shared_events.list_flow_events",
        lambda **_kwargs: [
            {
                "channel": "brains_test",
                "message_id": "lab-1",
                "timestamp": "2026-10-08T08:00:00Z",
                "outcome": "replied",
                "tenant_id": "linas",
                "user_message": "QA-LINAS-R2",
                "bot_to_user": "ok",
            }
        ],
    )
    from modules.platform_message_api import platform_message_flows

    result = asyncio.run(platform_message_flows(request=None, tenant_id=None, limit=50))
    assert result["messages"][0]["source"] == "lab"
    assert result["messages"][0]["channel"] == "brains_test"
    assert any(row.get("operation_id") == "out-1" for row in result["messages"])


def test_translations_keep_names_codes_and_the_label() -> None:
    from services.owner_portal.franco import keep_verbatim

    source = "QA-LINAS-RETEST The amber-falcon refund code is 5293."
    assert keep_verbatim(source, "Le code de remboursement est 5293.") == source
    kept = keep_verbatim(source, "QA-LINAS-RETEST Le code amber-falcon est 5293.")
    assert "amber-falcon" in kept and "5293" in kept and kept.startswith("QA-LINAS-RETEST")


def test_search_forms_keep_a_label_free_copy() -> None:
    from services.owner_portal.owner_qa import search_forms

    forms = search_forms("QA-LINAS-R2 what is the amber-falcon refund code?")
    assert forms[0].startswith("QA-LINAS-R2")
    assert forms[1] == "what is the amber-falcon refund code?"


def test_embed_retries_a_rate_limit(monkeypatch) -> None:
    from services.owner_portal.owner_embed import embed_one

    calls = {"n": 0}

    class _Response:
        def __init__(self, code: int) -> None:
            self.status_code = code

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError("rate limited")

        def json(self) -> dict:
            return {"data": [{"embedding": [0.2, 0.4]}]}

    def _post(*_args, **_kwargs):
        calls["n"] += 1
        return _Response(429 if calls["n"] == 1 else 200)

    monkeypatch.setattr("services.owner_portal.owner_embed.httpx.post", _post)
    monkeypatch.setattr("services.owner_portal.owner_embed.voyage_api_key", lambda: "test-key")
    monkeypatch.setattr("services.owner_portal.owner_embed.time.sleep", lambda _seconds: None)
    assert embed_one("amber-falcon refund", query=True) == [0.2, 0.4]
    assert calls["n"] == 2


def test_overview_totals_use_live_message_lots() -> None:
    import inspect

    from services.owner_portal.analytics_sql import load_overview

    source = inspect.getsource(load_overview)
    assert "SUM(l.remaining)" in source
    assert "period_id" in source
    assert "SUM(granted)" not in source


def test_version_uses_git_sha_or_unknown(monkeypatch) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.setenv("LINAS_RELEASE_SHA_FILE", "/tmp/does-not-exist-linas-sha")
    assert git_sha() == "unknown"
    monkeypatch.setenv("GIT_SHA", "3c514e11af1389a6eb0acfe26f132c5924ed6269")
    assert short_sha() == "3c514e11af13"
    assert os.environ["GIT_SHA"].startswith(short_sha())
