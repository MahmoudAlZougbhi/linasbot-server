#!/usr/bin/env python3
"""Audit or sanitize plaintext Meta credentials in historical inbound ledgers.

The command is read-only unless ``--apply`` is supplied. Output is restricted
to fixed labels and counts; credential values and event payloads are never
rendered. A dry-run exits nonzero whenever unsafe rows remain.
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

ENV_PATH_VARIABLE = "META_LEDGER_SANITIZE_ENV_FILE"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="replace unsafe settings snapshots; omission performs a dry-run",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="scan only local ledger files and do not connect to Firestore",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help=f"dotenv file to load before runtime imports (or ${ENV_PATH_VARIABLE})",
    )
    return parser


def _load_runtime_environment(path: Path | None) -> None:
    raw_path = str(path or os.getenv(ENV_PATH_VARIABLE) or "").strip()
    if raw_path:
        env_path = Path(raw_path).expanduser()
        if not env_path.is_file():
            raise RuntimeError("Configured sanitizer environment file is unavailable")
        load_dotenv(dotenv_path=env_path, override=False)
        return

    default_path = Path.cwd() / ".env"
    if default_path.is_file():
        load_dotenv(dotenv_path=default_path, override=False)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    mode = "apply" if args.apply else "dry-run"
    try:
        # Storage paths and Firestore configuration are resolved during service
        # imports, so dotenv parsing must happen first.
        _load_runtime_environment(args.env_file)
        project_root = str(PROJECT_ROOT)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        # Runtime initialization and third-party clients have their own console
        # logging. Suppress it so this security command emits only its fixed,
        # count-only result schema.
        with open(os.devnull, "w", encoding="utf-8") as output_sink:
            with redirect_stdout(output_sink), redirect_stderr(output_sink):
                from services.scale.inbound_event_store import sanitize_persisted_meta_credentials

                result = sanitize_persisted_meta_credentials(
                    apply=bool(args.apply),
                    include_firestore=not bool(args.local_only),
                )
        errors = int(result["local_errors"]) + int(result["firestore_errors"])
        changed = int(result["local_changed"]) + int(result["firestore_changed"])
        sanitized = int(result["local_sanitized"]) + int(result["firestore_sanitized"])
        remaining_unsafe = max(0, changed - sanitized) if args.apply else changed
        ok = errors == 0 and remaining_unsafe == 0
        output = {"ok": ok, "mode": mode, "remaining_unsafe": remaining_unsafe, **result}
        print(json.dumps(output, separators=(",", ":"), sort_keys=True))
        return 0 if ok else 2
    except Exception as exc:
        # Exception text from third-party clients may embed request details.
        # Report only its type so command output remains credential-safe.
        output = {"ok": False, "mode": mode, "error_type": type(exc).__name__}
        print(json.dumps(output, separators=(",", ":"), sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
