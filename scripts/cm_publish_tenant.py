#!/usr/bin/env python3
"""Wave 6 helper: seed/publish Linas tenant CM from existing draft defaults (local/rehearsal).

Does NOT deploy or flip production. Run on a machine with LINASBOT_DATA_ROOT pointed at
the target data root after reviewing drafts. Production cutover requires Mahmoud approval.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys


async def main() -> int:
    parser = argparse.ArgumentParser(description="Publish Linas CM content (rehearsal/local).")
    parser.add_argument("--tenant-id", default="linas")
    parser.add_argument("--published-by", default="wave6_migration")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        from services.cm.storage import ensure_defaults, get_draft
        from services.cm.constants import CM_SECTIONS

        ensure_defaults(tenant_id=args.tenant_id)
        print(f"[dry-run] tenant={args.tenant_id} data_root={os.getenv('LINASBOT_DATA_ROOT')}")
        for section in CM_SECTIONS:
            env = get_draft(section, tenant_id=args.tenant_id, create_default=True)
            print(f"  draft {section}: revision={env.revision} keys={list(env.payload.keys())[:8]}")
        return 0

    from services.cm.publish import publish_draft
    from services.cm.storage import ensure_defaults

    ensure_defaults(tenant_id=args.tenant_id)
    result = await publish_draft(tenant_id=args.tenant_id, published_by=args.published_by)
    print(
        f"[published] tenant={result.tenant_id} "
        f"content={result.content_version_id} index={result.index_version_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
