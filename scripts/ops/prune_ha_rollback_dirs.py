#!/usr/bin/env python3
"""Keep the newest HA rollback directories and delete older ones.

Dry-run unless --apply is set. Never touches the live app, data, or backup dirs.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

PREFIX = ".linasbot-ha-rollback-"
_NAME_RE = re.compile(r"\.linasbot-ha-rollback-[A-Za-z0-9._-]+")
_BACKUP_RE = re.compile(r"^[0-9a-f]{40}-[0-9]{14}-[0-9]+$")
_JOURNAL_FILES = (
    "deploy.active",
    "deploy-node.active",
    "transaction.json",
)


def rollback_dirs(root: Path) -> list[Path]:
    found: list[Path] = []
    if not root.is_dir():
        return found
    for path in root.iterdir():
        if path.is_symlink() or not path.is_dir():
            continue
        if path.name.startswith(PREFIX):
            found.append(path)
    return found


def backup_dirs(root: Path) -> list[Path]:
    found: list[Path] = []
    if not root.is_dir():
        return found
    for path in root.iterdir():
        if path.is_symlink() or not path.is_dir():
            continue
        if _BACKUP_RE.match(path.name):
            found.append(path)
    return found


def journal_names(state_root: Path) -> set[str]:
    names: set[str] = set()
    if not state_root.is_dir():
        return names
    for filename in _JOURNAL_FILES:
        path = state_root / filename
        if not path.is_file() or path.is_symlink():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        names.update(_NAME_RE.findall(text))
    return names


def select_dirs(
    dirs: list[Path],
    *,
    keep: int,
    protected_names: set[str],
) -> tuple[list[Path], list[Path]]:
    ordered = sorted(dirs, key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    kept = set(ordered[: max(keep, 0)])
    for path in ordered:
        if path.name in protected_names:
            kept.add(path)
    removed = [path for path in ordered if path not in kept]
    return sorted(kept, key=lambda path: path.name), removed


def _safe_target(root: Path, path: Path) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    if not (path.name.startswith(PREFIX) or _BACKUP_RE.match(path.name)):
        return False
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
    except OSError:
        return False
    return resolved.parent == root_resolved


def apply_removals(root: Path, removed: list[Path]) -> list[Path]:
    deleted: list[Path] = []
    for path in removed:
        if not _safe_target(root, path):
            continue
        shutil.rmtree(path)
        deleted.append(path)
    return deleted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prune old /opt HA rollback directories")
    parser.add_argument("--root", type=Path, default=Path("/opt"))
    parser.add_argument("--backup-root", type=Path, default=Path("/var/backups/linasbot-ha"))
    parser.add_argument("--state-root", type=Path, default=Path("/var/lib/linasbot/meta-ha"))
    parser.add_argument("--keep", type=int, default=3)
    parser.add_argument("--protect", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    protected = journal_names(args.state_root)
    for raw in args.protect:
        name = Path(raw).name
        if name.startswith(PREFIX):
            protected.add(name)
    kept, removed = select_dirs(rollback_dirs(args.root), keep=args.keep, protected_names=protected)
    backup_kept, backup_removed = select_dirs(backup_dirs(args.backup_root), keep=args.keep, protected_names=set())
    for path in kept + backup_kept:
        print(f"keep {path}")
    for path in removed + backup_removed:
        print(f"remove {path}")
    if args.apply:
        for path in apply_removals(args.root, removed) + apply_removals(args.backup_root, backup_removed):
            print(f"deleted {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
