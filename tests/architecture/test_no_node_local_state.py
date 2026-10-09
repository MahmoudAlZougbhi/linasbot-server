"""New service modules cannot grow node-local state without an allowlist edit."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(__file__).with_name("node_local_allowlist.txt")
NEEDLES = ("get_data_root", "atomic_write_json", "fcntl", "storage.persistent_storage")


def _offenders() -> set[str]:
    found: set[str] = set()
    for folder in ("services", "modules"):
        for path in (ROOT / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(needle in text for needle in NEEDLES):
                found.add(str(path.relative_to(ROOT)))
    return found


def test_node_local_imports_stay_on_the_allowlist() -> None:
    allowed = {line.strip() for line in ALLOWLIST.read_text(encoding="utf-8").splitlines() if line.strip()}
    assert _offenders() == allowed
