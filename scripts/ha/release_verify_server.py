#!/usr/bin/env python3
"""Side-effect-free precommit HTTP probe for an HA release.

Only the small application shell and the production health/readiness routes are
loaded.  In particular this entrypoint never imports the normal application
bootstrap, webhook handlers, migration bootstrap, queue consumers, or scheduler
startup.  Public readiness always honors the durable maintenance marker; the
separate one-shot target helper runs dependency checks without an HTTP bypass.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

HOST = "0.0.0.0"
PORT = 8003
MAINTENANCE = Path("/var/lib/linasbot/meta-ha/maintenance")
REPO = Path("/opt/linasbot")


def _required_environment() -> str:
    if os.environ.get("LINAS_HA_VERIFY_ONLY") != "true":
        raise RuntimeError("HA verification-only mode is not explicit")
    release = os.environ.get("LINAS_HA_VERIFY_RELEASE_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", release) is None:
        raise RuntimeError("HA verification release SHA is invalid")
    if not MAINTENANCE.is_file() or MAINTENANCE.is_symlink():
        raise RuntimeError("persistent maintenance authority is missing")
    return release


def verification_app() -> Any:
    # These are intentionally the only Linas application imports in this
    # process. dashboard_api_health registers exactly /, /api/health and
    # /api/ready on the minimal core app.
    import modules.dashboard_api_health  # noqa: F401
    from modules.core import app

    allowed_paths = {"/", "/api/health", "/api/ready"}
    actual_paths = {str(getattr(route, "path", "")) for route in app.routes}
    if actual_paths != allowed_paths:
        raise RuntimeError("HA verification server route surface is not exact")
    forbidden = {"modules.event_handlers", "storage.migrate_bootstrap"}
    if forbidden.intersection(sys.modules):
        raise RuntimeError("HA verification server imported side-effectful application startup")
    return app


def main() -> None:
    _required_environment()
    if Path(__file__).resolve() != REPO / "scripts/ha/release_verify_server.py":
        raise RuntimeError("HA verification entrypoint path is not canonical")
    sys.path.insert(0, str(REPO))
    app = verification_app()
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
