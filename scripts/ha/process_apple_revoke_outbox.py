#!/usr/bin/env python3
"""Drain durable Apple Sign in with Apple token-revoke outbox.

Uses AuthKey .p8 via apple_secrets (never prints key material).

  python scripts/ha/process_apple_revoke_outbox.py
  python scripts/ha/process_apple_revoke_outbox.py --limit 50
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process pending Apple token revokes")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args(argv)

    from services.apple_revoke_outbox import process_pending_revokes
    from services.apple_secrets import apple_sign_in_key_id, apple_sign_in_key_path

    # Paths + key id only — never PEM.
    print(
        json.dumps(
            {
                "ok": True,
                "mode": "start",
                "auth_key_id": apple_sign_in_key_id(),
                "auth_key_path_configured": bool(apple_sign_in_key_path()),
            }
        )
    )
    result = process_pending_revokes(limit=max(1, int(args.limit)))
    print(json.dumps({"ok": True, **result}))
    return 0 if int(result.get("errors") or 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
