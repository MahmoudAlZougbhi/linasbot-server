#!/usr/bin/env python3
"""Upsert Sol/Terra model-routing env keys (no service restart)."""

from __future__ import annotations

import os
import sys

# Ensure app import path when invoked from deploy.sh
_app = os.environ.get("CM_PRESERVE_APP_DIR") or "/opt/linasbot"
if _app not in sys.path:
    sys.path.insert(0, _app)

from services.cm.durable_flags import default_production_env_paths, upsert_env_file  # noqa: E402

UPDATES = {
    "LINAS_OWNER_MODEL": "gpt-5.6-sol",
    "LINAS_OWNER_HELP_MODEL": "gpt-5.6-sol",
    "LINAS_OWNER_CM_MODEL": "gpt-5.6-sol",
    "LINAS_MODEL_OWNER_CHAT": "gpt-5.6-sol",
    "LINAS_MODEL_SETUP": "gpt-5.6-sol",
    "LINAS_MODEL_CREATIVE": "gpt-5.6-sol",
    "LINAS_CREATIVE_MODEL": "gpt-5.6-sol",
    "LINAS_CUSTOMER_MODEL": "gpt-5.6-terra",
    "LINAS_CM_ANSWER_MODEL": "gpt-5.6-terra",
    "LINAS_MODEL_CUSTOMER_DM": "gpt-5.6-terra",
    "LINAS_CUSTOMER_HV_MODEL": "gpt-5.6-terra",
}


def main() -> int:
    app_dir = os.environ.get("CM_PRESERVE_APP_DIR") or "/opt/linasbot"
    touched = 0
    for path in default_production_env_paths(app_dir=app_dir):
        if not path.parent.exists():
            continue
        upsert_env_file(path, UPDATES)
        print(f"[model-routing] upserted path={path} keys={sorted(UPDATES)}")
        touched += 1
    if touched == 0:
        print("[model-routing] no env paths found to update", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
