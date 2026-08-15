#!/usr/bin/env python3
"""Upsert Sol/Terra routing in the canonical env under the common HA lock."""

from __future__ import annotations

import os
import sys

# Ensure the app import path when invoked by the reviewed HA release coordinator.
_app = os.environ.get("CM_PRESERVE_APP_DIR") or "/opt/linasbot"
if _app not in sys.path:
    sys.path.insert(0, _app)

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
    from scripts.ha.production_env_cas import atomic_update_canonical_env

    atomic_update_canonical_env(UPDATES)
    print(f"[model-routing] upserted path=/opt/linasbot/.env keys={sorted(UPDATES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
