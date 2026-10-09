"""Guards, dry-run imports, retention, and migration safety."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from scripts.ci.check_migrations import main as migration_main
from scripts.migrate.cm_merge_nodes import choose_newer, plan
from scripts.migrate.firestore_livechat_to_pg import summarize
from scripts.migrate.media_to_spaces import plan as media_plan
from services.platform.retention import purge_realtime_events
from services.platform.revision_header import StaleConfigRead, observe_revision, reset_for_tests
from services.platform.startup_guard import SharedStoreConfigError, assert_shared_stores_configured
from services.realtime.event_log import ensure_schema
from tests.architecture.test_no_node_local_state import NEEDLES


def _engine():
    path = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    path.close()
    engine = create_engine(
        f"sqlite:///{path.name}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    ensure_schema(engine)
    return engine


def test_unset_valkey_refuses_startup_when_shared_stores_are_required(monkeypatch) -> None:
    monkeypatch.setenv("LINAS_REQUIRE_SHARED_STORES", "1")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("LINAS_REDIS_URL", raising=False)
    monkeypatch.delenv("LINAS_PLATFORM_DATABASE_URL", raising=False)
    monkeypatch.delenv("LINAS_WHATSAPP_DATABASE_URL", raising=False)
    for name in ("LINAS_SPACES_KEY", "LINAS_SPACES_SECRET", "LINAS_SPACES_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SharedStoreConfigError):
        assert_shared_stores_configured()


def test_guard_is_off_unless_requested(monkeypatch) -> None:
    monkeypatch.delenv("LINAS_REQUIRE_SHARED_STORES", raising=False)
    assert_shared_stores_configured()


def test_revision_header_is_monotonic() -> None:
    reset_for_tests()
    first = observe_revision("qa-staging", 2)
    assert first["X-Config-Revision"] == "2"
    observe_revision("qa-staging", 3)
    with pytest.raises(StaleConfigRead):
        observe_revision("qa-staging", 1)


def test_realtime_retention_deletes_old_rows() -> None:
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO realtime_events (id, tenant_id, channel, payload, created_at)
                VALUES (1, 'qa-staging', 'live', '{}', 10)
                """
            )
        )
    assert purge_realtime_events(engine, now=10 + (25 * 60 * 60)) == 1


def test_cm_merge_picks_the_newer_pointer(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    for root, revision in ((left, 1), (right, 4)):
        pointer = root / "tenants" / "linas"
        pointer.mkdir(parents=True)
        (pointer / "pointer.json").write_text(
            json.dumps({"revision": revision, "published_at": f"2026-10-0{revision}T00:00:00Z"}),
            encoding="utf-8",
        )
    rows = plan(left, right)
    assert rows[0]["tenant"] == "linas"
    assert rows[0]["winner"] == "right"
    assert rows[0]["manual_review"] is True
    assert choose_newer({"revision": 2}, {"revision": 2}) == "left"


def test_media_plan_flags_conflicting_hashes(tmp_path: Path) -> None:
    left = tmp_path / "a"
    right = tmp_path / "b"
    left.mkdir()
    right.mkdir()
    (left / "prdim_1.bin").write_bytes(b"one")
    (right / "prdim_1.bin").write_bytes(b"two")
    report = media_plan([left, right])
    assert report["flagged"][0]["media_id"] == "prdim_1"


def test_messages_stay_inside_one_tenant() -> None:
    from services.live_chat.pg_history import append_message

    engine = _engine()
    append_message(engine, tenant_id="tenant-a", conversation_id="c1", body="a")
    append_message(engine, tenant_id="tenant-b", conversation_id="c1", body="b")
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT body FROM messages WHERE tenant_id = :tenant"), {"tenant": "tenant-a"}
        ).fetchall()
    assert [row.body for row in rows] == ["a"]


def test_livechat_export_checksum_is_stable() -> None:
    rows = [{"tenant_id": "qa-staging", "body": "hi"}]
    assert summarize(rows)["checksum"] == summarize(rows)["checksum"]
    assert summarize(rows)["by_tenant"]["qa-staging"] == 1


def test_current_migrations_pass_the_safety_check() -> None:
    assert migration_main() == 0


def test_drop_column_in_upgrade_is_rejected(tmp_path: Path) -> None:
    from scripts.ci.check_migrations import violations

    path = tmp_path / "20261010_bad.py"
    path.write_text("def upgrade():\n    op.drop_column('t', 'c')\n", encoding="utf-8")
    assert violations(path)


def test_planted_disk_import_matches_the_lint_needles() -> None:
    planted = "from storage.persistent_storage import get_data_root\n"
    assert any(needle in planted for needle in NEEDLES)
    allowlist = Path("tests/architecture/node_local_allowlist.txt").read_text(encoding="utf-8")
    assert "services/planted_violation.py" not in allowlist
