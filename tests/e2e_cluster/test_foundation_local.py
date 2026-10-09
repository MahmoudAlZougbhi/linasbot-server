"""Local stand-in for the staging pod checks. This does not talk to the cluster."""

from __future__ import annotations

import tempfile

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from services.ai_setup.pg_publish import publish, read_published
from services.config_revision.store import ensure_schema, set_engine_for_tests
from services.platform.revision_header import observe_revision, reset_for_tests
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


def test_two_readers_see_the_same_published_revision() -> None:
    engine = _engine()
    published = publish(engine, tenant_id="qa-staging", content={"hello": True}, published_by="owner")
    reset_for_tests()
    left = read_published(engine, "qa-staging")
    right = read_published(engine, "qa-staging")
    assert left == right
    assert left["revision"] == published["revision"]
    observe_revision("qa-staging", left["revision"])
    observe_revision("qa-staging", right["revision"])


def test_replay_fills_events_missed_by_a_dead_pod() -> None:
    engine = _engine()
    first = append_event(engine, tenant_id="qa-staging", channel="live_chat", payload={"n": 1})
    append_event(engine, tenant_id="qa-staging", channel="live_chat", payload={"n": 2})
    missed = replay_after(engine, tenant_id="qa-staging", last_event_id=first)
    assert [item["payload"]["n"] for item in missed] == [2]


def test_upload_on_one_store_is_readable_by_another_handle() -> None:
    store = DiskBlobStore()
    meta = store.put(tenant_id="qa-staging", media_id="prdim_9", content=b"img", mime="image/png")
    other = store.get(tenant_id="qa-staging", media_id="prdim_9")
    assert other is not None
    assert other[1].sha256 == meta.sha256
