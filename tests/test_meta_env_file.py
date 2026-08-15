from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.ha.meta_env_file import atomic_update_env


def test_atomic_update_deduplicates_targets_and_preserves_unrelated_lines(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "# keep\nENVIRONMENT=production\nMETA_APP_ID=old\nMETA_APP_ID=duplicate\nREMOVE_ME=yes\n",
        encoding="utf-8",
    )
    path.chmod(0o600)

    atomic_update_env(
        path,
        {"META_APP_ID": "2963733803971681", "META_APP_SECRET": "secret-value"},
        remove_keys=frozenset({"REMOVE_ME"}),
    )

    text = path.read_text(encoding="utf-8")
    assert text.count("META_APP_ID=") == 1
    assert "META_APP_ID=2963733803971681" in text
    assert "META_APP_SECRET=secret-value" in text
    assert "ENVIRONMENT=production" in text
    assert "REMOVE_ME" not in text
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".env.meta-stage.*"))


@pytest.mark.parametrize(
    ("updates", "remove_keys"),
    [
        ({"bad-key": "value"}, frozenset()),
        ({"META_APP_SECRET": "secret\nsecond-line"}, frozenset()),
        ({"META_APP_ID": "value"}, frozenset({"META_APP_ID"})),
    ],
)
def test_atomic_update_rejects_invalid_entries(
    tmp_path: Path,
    updates: dict[str, str],
    remove_keys: frozenset[str],
) -> None:
    path = tmp_path / ".env"
    path.write_text("ENVIRONMENT=production\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        atomic_update_env(path, updates, remove_keys=remove_keys)


def test_atomic_update_refuses_missing_or_symlinked_canonical_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.env"
    with pytest.raises(RuntimeError, match="unavailable"):
        atomic_update_env(missing, {"META_APP_ID": "value"})

    target = tmp_path / "target.env"
    target.write_text("ENVIRONMENT=production\n", encoding="utf-8")
    link = tmp_path / ".env"
    link.symlink_to(target)
    with pytest.raises(RuntimeError, match="security contract"):
        atomic_update_env(link, {"META_APP_ID": "value"})


def test_canonical_environment_rejects_world_readable_mode(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("META_APP_ID=2963733803971681\n", encoding="utf-8")
    path.chmod(0o644)

    with pytest.raises(RuntimeError, match="security contract"):
        atomic_update_env(path, {"META_APP_SECRET": "secret-value"})


def test_canonical_environment_rejects_foreign_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / ".env"
    path.write_text("META_APP_ID=2963733803971681\n", encoding="utf-8")
    path.chmod(0o600)
    monkeypatch.setattr(os, "geteuid", lambda: path.stat().st_uid + 1)

    with pytest.raises(RuntimeError, match="security contract"):
        atomic_update_env(path, {"META_APP_SECRET": "secret-value"})
