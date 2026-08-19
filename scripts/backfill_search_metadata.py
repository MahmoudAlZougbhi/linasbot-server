"""Optional offline backfill for search metadata. Do NOT run on production.

Usage (staging/local only):

  python -m scripts.backfill_search_metadata --tenant TENANT_ID --dry-run
  python -m scripts.backfill_search_metadata --tenant TENANT_ID --execute --section knowledge

Runtime Customer Reply works without this job: missing ai_search_* falls back to original titles.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill English search metadata (not for production).")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--section", default="", help="Optional CM section name; omit for all metadata sections.")
    parser.add_argument("--products", action="store_true", help="Also backfill product rows for the tenant.")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true", help="Actually write. Default is dry-run.")
    args = parser.parse_args(argv)
    dry = not args.execute
    print("backfill_search_metadata: DO NOT RUN ON PRODUCTION.")
    print(f"tenant={args.tenant} section={args.section or '*'} products={args.products} dry_run={dry}")
    if dry:
        print("dry-run: no writes. Pass --execute on a non-production environment after review.")
        return 0
    print("execute path is intentionally unimplemented here to prevent accidental production writes.")
    print("Use Save on each changed item, or a reviewed staging script.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
