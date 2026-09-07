#!/usr/bin/env python3
"""Read-only Enhanced Video Context probe for a connected tenant (default linas)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Read-only TikTok enhanced post-context probe")
    parser.add_argument("--tenant-id", default="linas")
    args = parser.parse_args()
    from services.tiktok_business.live_probe import probe_linas_enhanced_readonly

    result = await probe_linas_enhanced_readonly(tenant_id=args.tenant_id)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("acceptable") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
