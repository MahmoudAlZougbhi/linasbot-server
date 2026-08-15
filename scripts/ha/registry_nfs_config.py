#!/usr/bin/env python3
"""Exact, byte-preserving parsers for Meta registry NFS configuration.

The retirement shell script must never use substring or regular-expression
matching for a destructive config edit.  This helper matches parsed fields and
prints either a count or a filtered copy while preserving every unrelated line.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

NFS_TYPES = frozenset({"nfs", "nfs4"})


def _fields(line: str) -> list[str]:
    stripped = line.lstrip()
    if not stripped or stripped.startswith("#"):
        return []
    return line.split()


def fstab_entry_matches(line: str, *, source: str, target: str) -> bool:
    fields = _fields(line)
    return len(fields) >= 3 and fields[0] == source and fields[1] == target and fields[2] in NFS_TYPES


def export_entry_matches(line: str, *, target: str) -> bool:
    fields = _fields(line)
    return bool(fields) and fields[0] == target


def exact_count(lines: list[str], matcher: Callable[[str], bool]) -> int:
    return sum(1 for line in lines if matcher(line))


def filtered_text(lines: list[str], matcher: Callable[[str], bool]) -> str:
    return "".join(line for line in lines if not matcher(line))


def selected_text(lines: list[str], matcher: Callable[[str], bool]) -> str:
    return "".join(line for line in lines if matcher(line))


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="strict").splitlines(keepends=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "kind",
        choices=(
            "fstab-count",
            "fstab-filter",
            "exports-count",
            "exports-filter",
            "exports-select",
        ),
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--source", default="")
    parser.add_argument("--target", required=True)
    args = parser.parse_args(argv)
    lines = _read_lines(args.path)
    if args.kind.startswith("fstab"):
        if not args.source:
            parser.error("fstab operations require --source")
        matcher = partial(fstab_entry_matches, source=args.source, target=args.target)
    else:
        matcher = partial(export_entry_matches, target=args.target)
    if args.kind.endswith("count"):
        print(exact_count(lines, matcher))
    elif args.kind.endswith("select"):
        sys.stdout.write(selected_text(lines, matcher))
    else:
        sys.stdout.write(filtered_text(lines, matcher))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
