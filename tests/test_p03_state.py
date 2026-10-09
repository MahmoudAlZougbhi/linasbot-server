"""Shared-store paths stay off until their flags are set."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from scripts.ops.node_state_audit import categorize
from scripts.ops.node_state_audit import main as audit_main
from services.ai_setup.pg_publish import StaleRevision, publish, read_published
from services.config_revision.store import DOMAINS, bump, current, ensure_schema, set_engine_for_tests
from services.live_chat.pg_history import append_message
from services.platform.feature_flags import flag_value
from services.realtime.event_log import append_event, replay_after
from services.storage.blob_store import DiskBlobStore


def _engine():
    path = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    path.close()
    engine = create_engine(
        f"sqlite:///{path.name}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    ensure_schema(engine)
    set_engine_for_tests(engine)
    return engine


def test_flags_keep_the_disk_paths(monkeypatch) -> None:
    monkeypatch.delenv("LINAS_FLAG_CM_STORE", raising=False)
    monkeypatch.delenv("LINAS_FLAG_MEDIA_STORE", raising=False)
    monkeypatch.delenv("LINAS_FLAG_LIVECHAT_STORE", raising=False)
    assert flag_value("cm_store") == "disk"
    assert flag_value("media_store") == "disk"
    assert flag_value("livechat_store") == "firestore"


def test_publish_is_atomic_and_rejects_a_stale_revision() -> None:
    engine = _engine()
    first = publish(engine, tenant_id="qa-staging", content={"section": "requests"}, published_by="owner")
    second = publish(
        engine,
        tenant_id="qa-staging",
        content={"section": "requests", "on": True},
        published_by="owner",
        expected_revision=first["revision"],
    )
    assert second["revision"] == first["revision"] + 1
    assert read_published(engine, "qa-staging")["checksum"] == second["checksum"]
    try:
        publish(
            engine,
            tenant_id="qa-staging",
            content={"section": "requests"},
            published_by="owner",
            expected_revision=first["revision"],
        )
    except StaleRevision as exc:
        assert exc.http_status == 412
    else:
        raise AssertionError("stale publish was accepted")
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) AS n FROM cm_versions")).one().n
    assert int(count) == 2


def test_every_domain_revision_is_visible_to_another_reader() -> None:
    engine = _engine()
    for domain in DOMAINS:
        with engine.begin() as conn:
            revision = bump(conn, "qa-staging", domain)
        assert revision == 1
        assert current("qa-staging", domain, engine=engine) == 1


def test_live_chat_counter_and_realtime_replay() -> None:
    engine = _engine()
    append_message(engine, tenant_id="qa-staging", conversation_id="c1", body="hello")
    append_message(engine, tenant_id="qa-staging", conversation_id="c1", body="again")
    with engine.connect() as conn:
        unread = (
            conn.execute(text("SELECT unread_count FROM conversations WHERE conversation_id = 'c1'")).one().unread_count
        )
    assert int(unread) == 2
    first = append_event(engine, tenant_id="qa-staging", channel="live_chat", payload={"body": "hello"})
    append_event(engine, tenant_id="qa-staging", channel="live_chat", payload={"body": "again"})
    missed = replay_after(engine, tenant_id="qa-staging", last_event_id=first)
    assert [item["payload"]["body"] for item in missed] == ["again"]


def test_blob_round_trip_matches_sha256() -> None:
    store = DiskBlobStore()
    content = b"png-bytes"
    meta = store.put(tenant_id="qa-staging", media_id="prdim_1", content=content, mime="image/png")
    loaded = store.get(tenant_id="qa-staging", media_id="prdim_1")
    assert loaded is not None
    assert loaded[0] == content
    assert loaded[1].sha256 == meta.sha256


def test_audit_categories_cover_known_paths(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "tenants" / "linas" / "cm").mkdir(parents=True)
    (root / "tenants" / "linas" / "cm" / "pointer.json").write_text("{}", encoding="utf-8")
    (root / "smart_messaging").mkdir()
    (root / "smart_messaging" / "message_queue.json").write_text("[]", encoding="utf-8")
    assert categorize("tenants/linas/cm/pointer.json") == "cm"
    assert categorize("smart_messaging/message_queue.json") == "smart_messaging"
    for path in root.rglob("*"):
        path.chmod(0o555)
    root.chmod(0o555)
    assert audit_main([str(root), "--summary-only"]) == 0
