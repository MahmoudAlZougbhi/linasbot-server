#!/usr/bin/env python3
"""CLI: run CM fixture migration and write a conflict report (plan Phase 4).

Only ever targets fixture/local test data — never a live production data root — and only
writes under the target tenant's CM draft/archive subtree. Intended for local/dry rehearsal,
not production cutover.

Usage:
    python scripts/cm/run_migration_dry.py \\
        --source tests/fixtures/cm_migration \\
        --tenant-id migration_dry_run \\
        --out docs/cm_phase_evidence/phase4_migration_conflict_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.cm.migration import migrate_legacy_fixture  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, help="Fixture/legacy root directory (contains legacy/ + manifest.json)"
    )
    parser.add_argument("--tenant-id", required=True, help="Target CM tenant id for the migrated draft")
    parser.add_argument("--out", required=True, help="Output JSON report path")
    parser.add_argument("--updated-by", default="migration_dry_run", help="Attribution for draft writes")
    args = parser.parse_args()

    report = migrate_legacy_fixture(
        source_root=args.source,
        tenant_id=args.tenant_id,
        updated_by=args.updated_by,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Migration dry run complete for tenant={args.tenant_id!r}")
    print(f"  FAQ groups imported:      {report['faq_groups_imported']}")
    print(f"  Knowledge articles:       {report['knowledge_articles_imported']}")
    print(f"  Care articles:            {report['care_articles_imported']}")
    print(f"  Handoff contacts:         {report['handoff_contacts_imported']}")
    print(f"  Archived legacy files:    {len(report['archived_files'])}")
    print(f"  Restricted conflicts:     {report['conflict_count']}")
    print(f"Report written to {out_path}")

    if report["conflict_count"]:
        print("\nConflicts (hard publish blockers until resolved):")
        for conflict in report["conflicts"]:
            print(f"  - [{conflict['code']}] {conflict['message']}")


if __name__ == "__main__":
    main()
