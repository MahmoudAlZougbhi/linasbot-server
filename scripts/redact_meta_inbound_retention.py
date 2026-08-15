#!/usr/bin/env python3
"""Audit or redact expired terminal Meta inbound payloads without rendering data.

The command is read-only unless ``--apply`` is supplied. A dirty dry-run exits
with status 3; store/read/write failures exit with status 2. Production callers
must provide the deployed dotenv path explicitly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH_VARIABLE = "META_INBOUND_RETENTION_ENV_FILE"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="redact expired terminal payloads; omission performs a dry-run",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help=f"required deployed dotenv file (or ${ENV_PATH_VARIABLE})",
    )
    return parser


def _load_runtime_environment(path: Path | None) -> None:
    raw_path = str(path or os.getenv(ENV_PATH_VARIABLE) or "").strip()
    if not raw_path:
        raise RuntimeError("Retention environment file is required")
    env_path = Path(raw_path).expanduser()
    if not env_path.is_file():
        raise RuntimeError("Configured retention environment file is unavailable")
    load_dotenv(dotenv_path=env_path, override=False)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    mode = "apply" if args.apply else "dry-run"
    try:
        _load_runtime_environment(args.env_file)
        project_root = str(PROJECT_ROOT)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        with open(os.devnull, "w", encoding="utf-8") as output_sink:
            with redirect_stdout(output_sink), redirect_stderr(output_sink):
                from services.meta_inbound_retention import redact_expired_terminal_inbound_events

                result = redact_expired_terminal_inbound_events(
                    apply=bool(args.apply),
                    include_firestore=True,
                )
        errors = int(result["local_errors"]) + int(result["firestore_errors"])
        changed = int(result["local_changed"]) + int(result["firestore_changed"])
        redacted = int(result["local_redacted"]) + int(result["firestore_redacted"])
        remaining = max(0, changed - redacted) if args.apply else changed
        stores_ok = bool(result["firestore_available"])
        ok = errors == 0 and stores_ok and remaining == 0
        output = {"ok": ok, "mode": mode, "remaining_expired": remaining, **result}
        print(json.dumps(output, separators=(",", ":"), sort_keys=True))
        if ok:
            return 0
        return 3 if not args.apply and errors == 0 and stores_ok and remaining else 2
    except Exception as exc:
        output = {"ok": False, "mode": mode, "error_type": type(exc).__name__}
        print(json.dumps(output, separators=(",", ":"), sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
