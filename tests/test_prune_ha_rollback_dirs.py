from __future__ import annotations

import os
import time
from pathlib import Path

from scripts.ops.prune_ha_rollback_dirs import journal_names, select_dirs


def _touch(path: Path, when: float) -> None:
    path.mkdir()
    os.utime(path, (when, when))


def test_select_dirs_keeps_newest_three_and_journal_names(tmp_path: Path) -> None:
    root = tmp_path / "opt"
    root.mkdir()
    base = 1_700_000_000
    for index in range(5):
        _touch(root / f".linasbot-ha-rollback-sha{index}-2026010{index}000000-1", base + index)
    (root / "linasbot").mkdir()
    (root / "linasbot_data").mkdir()
    dirs = [path for path in root.iterdir() if path.name.startswith(".linasbot-ha-rollback-")]
    kept, removed = select_dirs(
        dirs,
        keep=3,
        protected_names={".linasbot-ha-rollback-sha0-20260100000000-1"},
    )
    kept_names = {path.name for path in kept}
    assert ".linasbot-ha-rollback-sha0-20260100000000-1" in kept_names
    assert ".linasbot-ha-rollback-sha4-20260104000000-1" in kept_names
    assert len(removed) == 1
    assert not any(path.name in {"linasbot", "linasbot_data"} for path in removed)


def test_journal_names_reads_only_rollback_tokens(tmp_path: Path) -> None:
    state = tmp_path / "meta-ha"
    state.mkdir()
    (state / "deploy.active").write_text(
        "open /opt/.linasbot-ha-rollback-abc-20260101120000-9 recovery_status\n",
        encoding="utf-8",
    )
    names = journal_names(state)
    assert names == {".linasbot-ha-rollback-abc-20260101120000-9"}


def test_backup_dirs_ignore_untracked_names(tmp_path: Path) -> None:
    from scripts.ops.prune_ha_rollback_dirs import backup_dirs

    root = tmp_path / "linasbot-ha"
    root.mkdir()
    (root / "untracked-quarantine").mkdir()
    (root / "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-20261008191855-1").mkdir()
    names = {path.name for path in backup_dirs(root)}
    assert names == {"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-20261008191855-1"}


def test_select_dirs_orders_newest_first(tmp_path: Path) -> None:
    root = tmp_path
    older = root / ".linasbot-ha-rollback-old"
    newer = root / ".linasbot-ha-rollback-new"
    _touch(older, time.time() - 100)
    _touch(newer, time.time())
    kept, removed = select_dirs([older, newer], keep=1, protected_names=set())
    assert [path.name for path in kept] == [".linasbot-ha-rollback-new"]
    assert [path.name for path in removed] == [".linasbot-ha-rollback-old"]
