"""Tests for exact-release Alembic migration authority."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from scripts.ha.release_alembic_migrate import (
    LEGACY_PRE_MERGE_STAMPS,
    _assert_runtime_environment,
    _normalize_repo_relative_path,
    _script_directory,
    ancestors_of,
    assert_canonical_release_tree,
    git_ls_files_others_command,
    load_migration_env_snapshot,
    prepare_migration_authority,
    reject_untracked_migration_paths,
    validate_stamped_before,
)
from tests.docker_test_containers import docker_available, start_disposable_postgres
from tests.web_chat_acceptance_support import (
    _alembic_python,
    _ensure_psycopg2,
    _wait_for_postgres,
)

ROOT = Path(__file__).resolve().parents[1]
HEAD_ID = "20260826_meta_comment_perm"


@pytest.fixture()
def postgres_url() -> Iterator[str]:
    _ensure_psycopg2()
    configured = (os.getenv("LINAS_TEST_ALEMBIC_POSTGRES_URL") or "").strip()
    if configured:
        from sqlalchemy.engine import make_url

        parsed = make_url(configured)
        if not parsed.drivername.startswith("postgresql"):
            pytest.fail("LINAS_TEST_ALEMBIC_POSTGRES_URL must be PostgreSQL")
        if (parsed.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
            pytest.fail("LINAS_TEST_ALEMBIC_POSTGRES_URL must be local disposable PostgreSQL")
        _wait_for_postgres(configured)
        yield configured
        return
    if not docker_available():
        pytest.fail("Docker is required for disposable PostgreSQL alembic migration tests")
    generator = start_disposable_postgres(
        db_name="release_alembic_migrate",
        container_prefix="linas-web-chat-ha",
        wait_for_ready=_wait_for_postgres,
    )
    url = next(generator)
    try:
        yield url
    finally:
        generator.close()


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    python_bin = _alembic_python()
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["LINAS_WHATSAPP_DATABASE_URL"] = url
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [python_bin, "-m", "alembic", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _stamped(url: str) -> set[str]:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).all()
    return {str(row[0]) for row in rows}


def _git_ls_files_response(command: list[str], stdout: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(command, 0, stdout, b"")


def _fake_canonical_git_run(head: str, *, non_ignored: bytes = b"", ignored: bytes = b""):
    from scripts.ha.release_alembic_migrate import git_ls_files_others_command

    def fake_run(command, **kwargs):
        if command[-2:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, head + "\n", "")
        if len(command) >= 2 and command[-2] == "--quiet":
            return subprocess.CompletedProcess(command, 0, "", "")
        if command == git_ls_files_others_command(ROOT, ignored=False):
            return _git_ls_files_response(command, non_ignored)
        if command == git_ls_files_others_command(ROOT, ignored=True):
            return _git_ls_files_response(command, ignored)
        return subprocess.run(command, **kwargs)

    return fake_run


def _current_head() -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_validate_rejects_empty_stamp() -> None:
    with pytest.raises(RuntimeError, match="empty"):
        validate_stamped_before(set(), expected_head=HEAD_ID)


def test_validate_accepts_legacy_pre_merge_two_head_stamp() -> None:
    validate_stamped_before(set(LEGACY_PRE_MERGE_STAMPS), expected_head=HEAD_ID)


def test_validate_rejects_unknown_non_ancestor_revision() -> None:
    with pytest.raises(RuntimeError, match="non-ancestor"):
        validate_stamped_before(
            {"20260813_sfu_channels_enabled", "bogus_unknown_revision"},
            expected_head=HEAD_ID,
        )


def test_validate_rejects_unreviewed_ancestor_pair_without_upgrade() -> None:
    with pytest.raises(RuntimeError, match="ambiguous"):
        validate_stamped_before(
            {"20260813_sfu_channels_enabled", "20260816_pending_downgrade"},
            expected_head=HEAD_ID,
        )


def test_assert_runtime_environment_rejects_pythonpath(monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "/tmp/evil")
    with pytest.raises(RuntimeError, match="forbidden environment key"):
        _assert_runtime_environment({"PYTHONPATH": "/tmp/evil"})


def test_assert_canonical_release_tree_rejects_head_mismatch() -> None:
    with pytest.raises(RuntimeError, match="HEAD does not match"):
        assert_canonical_release_tree("0" * 40)


def test_assert_runtime_environment_rejects_alembic_config(monkeypatch) -> None:
    monkeypatch.setenv("ALEMBIC_CONFIG", "/tmp/evil.ini")
    with pytest.raises(RuntimeError, match="forbidden environment key"):
        _assert_runtime_environment({"ALEMBIC_CONFIG": "/tmp/evil.ini"})


def test_assert_canonical_release_tree_rejects_tree_dirt(monkeypatch) -> None:
    head = _current_head()

    def fake_run(command, **kwargs):
        if command[-2:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, head + "\n", "")
        if len(command) >= 2 and command[-2] == "--quiet":
            return subprocess.CompletedProcess(command, 1, "", "")
        return subprocess.run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="tree/index/worktree"):
        assert_canonical_release_tree(head)


def test_load_migration_env_snapshot_reads_env_once(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://example\n", encoding="utf-8")
    calls = 0

    def fake_dotenv_values(path, **kwargs):
        nonlocal calls
        calls += 1
        assert path == env_file
        return {"DATABASE_URL": "postgresql://example"}

    monkeypatch.setattr("dotenv.dotenv_values", fake_dotenv_values)
    monkeypatch.setattr("scripts.ha.release_alembic_migrate.ENV_FILE", env_file)
    snapshot = load_migration_env_snapshot("a" * 40)
    assert calls == 1
    assert snapshot.mapping["LINAS_HA_VERIFY_RELEASE_SHA"] == "a" * 40


def test_prepare_migration_authority_rejects_second_env_read(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://example\n", encoding="utf-8")
    maintenance = tmp_path / "maintenance"
    maintenance.write_text("ok\n", encoding="utf-8")
    monkeypatch.setenv("LINAS_HA_VERIFY_ONLY", "true")
    monkeypatch.setenv("LINAS_HA_VERIFY_RELEASE_SHA", _current_head())
    monkeypatch.setenv("DATABASE_URL", "wrong")
    monkeypatch.setattr("scripts.ha.release_alembic_migrate.MAINTENANCE", maintenance)
    monkeypatch.setattr("scripts.ha.release_alembic_migrate.ENV_FILE", env_file)
    with pytest.raises(RuntimeError, match="stale canonical environment"):
        prepare_migration_authority()


def test_assert_canonical_release_tree_accepts_current_head(monkeypatch) -> None:
    head = _current_head()
    monkeypatch.setattr(subprocess, "run", _fake_canonical_git_run(head))
    assert_canonical_release_tree(head)


def test_ancestors_of_collects_string_revision_ids() -> None:
    script = _script_directory()
    ancestors = ancestors_of(script, HEAD_ID)
    assert HEAD_ID in ancestors
    assert ancestors
    assert all(isinstance(revision_id, str) for revision_id in ancestors)
    assert LEGACY_PRE_MERGE_STAMPS <= ancestors


class TestUntrackedMigrationAuthority:
    def test_git_ls_files_argv_shape_non_ignored(self) -> None:
        assert git_ls_files_others_command(ROOT, ignored=False) == [
            "git",
            "-C",
            str(ROOT),
            "ls-files",
            "-z",
            "--others",
            "--exclude-standard",
        ]

    def test_git_ls_files_argv_shape_ignored(self) -> None:
        assert git_ls_files_others_command(ROOT, ignored=True) == [
            "git",
            "-C",
            str(ROOT),
            "ls-files",
            "-z",
            "--others",
            "--exclude-standard",
            "--ignored",
        ]

    def test_rejects_non_ignored_untracked_alembic_migration(self, monkeypatch) -> None:
        head = _current_head()
        payload = b"alembic/versions/evil_untracked.py\x00"
        monkeypatch.setattr(subprocess, "run", _fake_canonical_git_run(head, non_ignored=payload))
        with pytest.raises(RuntimeError, match="untracked migration/config paths"):
            reject_untracked_migration_paths(ROOT)

    def test_rejects_ignored_untracked_alembic_migration_without_mutation(self, monkeypatch) -> None:
        head = _current_head()
        payload = b"alembic/versions/evil_ignored.py\x00"
        monkeypatch.setattr(subprocess, "run", _fake_canonical_git_run(head, ignored=payload))
        with pytest.raises(RuntimeError, match="ignored:alembic/versions/evil_ignored.py"):
            reject_untracked_migration_paths(ROOT)

    def test_rejects_non_ignored_untracked_alembic_ini(self, monkeypatch) -> None:
        head = _current_head()
        payload = b"alembic.ini\x00"
        monkeypatch.setattr(subprocess, "run", _fake_canonical_git_run(head, non_ignored=payload))
        with pytest.raises(RuntimeError, match="untracked:alembic.ini"):
            reject_untracked_migration_paths(ROOT)

    def test_rejects_newline_filename_without_mutation(self) -> None:
        with pytest.raises(RuntimeError, match="unsafe control characters"):
            _normalize_repo_relative_path(b"alembic/versions/evil.py\n")

    def test_rejects_quote_escaped_filename_without_mutation(self) -> None:
        with pytest.raises(RuntimeError, match="quote-escaped"):
            _normalize_repo_relative_path(b'"alembic/versions/evil.py"')

    def test_rejects_path_escape_without_mutation(self) -> None:
        with pytest.raises(RuntimeError, match="escapes repository root"):
            _normalize_repo_relative_path(b"alembic/../evil.py")


@pytest.mark.integration
def test_legacy_two_head_stamp_upgrades_to_single_head(postgres_url: str) -> None:
    assert _alembic(postgres_url, "upgrade", "20260813_sfu_channels_enabled").returncode == 0
    assert _alembic(postgres_url, "stamp", "--purge", *sorted(LEGACY_PRE_MERGE_STAMPS)).returncode == 0
    stamped = _stamped(postgres_url)
    assert stamped == set(LEGACY_PRE_MERGE_STAMPS)
    validate_stamped_before(stamped, expected_head=HEAD_ID)
    completed = _alembic(postgres_url, "upgrade", HEAD_ID)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert _stamped(postgres_url) == {HEAD_ID}


@pytest.mark.integration
def test_unknown_pair_is_rejected_without_mutation(postgres_url: str) -> None:
    assert _alembic(postgres_url, "stamp", "20260813_sfu_channels_enabled").returncode == 0
    engine = create_engine(postgres_url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('bogus_unknown_revision')"))
    before = _stamped(postgres_url)
    with pytest.raises(RuntimeError, match="non-ancestor"):
        validate_stamped_before(before, expected_head=HEAD_ID)
    assert _stamped(postgres_url) == before
