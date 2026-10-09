#!/usr/bin/env python3
"""Write the cluster env file from connection JSON and the process environment.

Prints only key names. Never prints values.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _row(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        payload = payload[0]
    if not isinstance(payload, dict):
        raise SystemExit(f"bad connection json: {path.name}")
    return payload


def _uri(path: Path) -> str:
    row = _row(path)
    uri = str(row.get("uri") or row.get("URI") or "").strip()
    if not uri:
        raise SystemExit(f"connection json has no uri: {path.name}")
    return uri


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: render_cluster_env.py pg.json redis.json out.env")
    values = {
        "LINAS_CONFIG_SOURCE": "env",
        "LINAS_LOG_FORMAT": "json",
        "LINAS_WHATSAPP_DATABASE_URL": _uri(Path(sys.argv[1])),
        "REDIS_URL": _uri(Path(sys.argv[2])),
    }
    for name in (
        "LINAS_SPACES_KEY",
        "LINAS_SPACES_SECRET",
        "LINAS_SPACES_BUCKET",
        "LINAS_SPACES_ENDPOINT",
        "LINAS_BACKUP_BUCKET",
        "OPENAI_API_KEY",
        "VOYAGE_API_KEY",
        "DASHBOARD_AUTH_SECRET",
        "SENTRY_DSN",
    ):
        raw = (os.environ.get(name) or "").strip()
        if raw:
            values[name] = raw
    lines = [f"{key}={values[key]}" for key in sorted(values)]
    Path(sys.argv[3]).write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(sys.argv[3], 0o600)
    print("env_keys", ",".join(sorted(values)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
