#!/usr/bin/env python3
"""
Delete ALL conversations and live_chat_index from Firestore. Use to start fresh.

WARNING: This is destructive. User docs (names, gender, etc.) are kept; only
conversations and index entries are deleted.

Defaults to dry-run. Execute requires ALL of:
  --execute
  --i-understand-delete-all-conversations  (exact typed phrase flag)
  LINAS_ALLOW_DESTRUCTIVE_CONVERSATION_DELETE=1 when the environment looks
  like production / real credentials

Usage:
  python archive/scripts/delete_all_conversations.py                  # dry-run (default)
  python archive/scripts/delete_all_conversations.py --dry-run         # explicit dry-run
  LINAS_ALLOW_DESTRUCTIVE_CONVERSATION_DELETE=1 \\
    python archive/scripts/delete_all_conversations.py --execute \\
      --i-understand-delete-all-conversations
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# archive/scripts/<file> → repo root is two levels up from this file's directory
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

CONFIRM_PHRASE = "I_UNDERSTAND_DELETE_ALL_CONVERSATIONS"
ALLOW_ENV = "LINAS_ALLOW_DESTRUCTIVE_CONVERSATION_DELETE"

APP_ID = "linas-ai-bot-backend"
BATCH_SIZE = 500


def _env_looks_like_production(environ: dict[str, str] | None = None) -> bool:
    """True when ENV/ENVIRONMENT/APP_MODE or credential paths look like real prod."""
    env = environ if environ is not None else os.environ
    for key in ("ENVIRONMENT", "ENV", "APP_ENV"):
        val = (env.get(key) or "").strip().lower()
        if val in {"prod", "production", "live"}:
            return True
    app_mode = (env.get("APP_MODE") or "").strip().lower()
    if app_mode in {"prod", "production", "live"}:
        return True
    # Real Firebase key present under the default prod path is treated as high risk.
    cred_path = (env.get("GOOGLE_APPLICATION_CREDENTIALS") or env.get("FIREBASE_CREDENTIALS") or "").strip()
    if cred_path and ("prod" in cred_path.lower() or "production" in cred_path.lower()):
        return True
    # HOSTNAME / deploy markers commonly set on the live VPS.
    host = (env.get("HOSTNAME") or "").strip().lower()
    if "linasaibot" in host or host.endswith("linasbot"):
        return True
    if (env.get("LINAS_DEPLOY_TARGET") or "").strip().lower() in {"prod", "production", "live"}:
        return True
    return False


def _has_real_looking_credentials(environ: dict[str, str] | None = None) -> bool:
    """True when Firebase / GCP creds appear configured (not empty stubs)."""
    env = environ if environ is not None else os.environ
    for key in ("GOOGLE_APPLICATION_CREDENTIALS", "FIREBASE_CREDENTIALS", "FIRESTORE_EMULATOR_HOST"):
        if (env.get(key) or "").strip():
            # Emulator host alone is safe — not "real" prod credentials.
            if key == "FIRESTORE_EMULATOR_HOST":
                continue
            return True
    # Default service-account file used by this repo.
    default_key = os.path.join(_REPO_ROOT, "data", "firebase_data.json")
    return os.path.isfile(default_key)


def assert_execute_allowed(
    *,
    execute: bool,
    confirm_phrase: str,
    environ: dict[str, str] | None = None,
    has_credentials: bool | None = None,
) -> None:
    """Raise SystemExit with a clear message if execute guards fail.

    Dry-run always allowed. Execute requires the exact phrase and, when the
    environment looks like production or real credentials are present, also
    LINAS_ALLOW_DESTRUCTIVE_CONVERSATION_DELETE=1.
    """
    if not execute:
        return
    env = environ if environ is not None else dict(os.environ)
    if (confirm_phrase or "").strip() != CONFIRM_PHRASE:
        raise SystemExit(
            f"❌ Refusing execute: pass --i-understand-delete-all-conversations "
            f"{CONFIRM_PHRASE} (exact phrase required)."
        )
    allow = (env.get(ALLOW_ENV) or "").strip() == "1"
    looks_prod = _env_looks_like_production(env)
    creds = _has_real_looking_credentials(env) if has_credentials is None else has_credentials
    if (looks_prod or creds) and not allow:
        raise SystemExit(
            "❌ Refusing execute: environment looks like production and/or real "
            f"Firebase credentials are present. Set {ALLOW_ENV}=1 AND the typed "
            f"phrase flag to proceed. Prefer dry-run."
        )


def run_delete(*, dry_run: bool, execute: bool, confirm_phrase: str = "") -> None:
    # Import lazily so unit tests can import guards without Firestore.
    import config
    from utils.utils import get_firestore_db

    conversations_collection = getattr(config, "FIRESTORE_CONVERSATIONS_COLLECTION", "conversations")

    assert_execute_allowed(execute=execute, confirm_phrase=confirm_phrase)

    if execute and not dry_run:
        print(
            "⚠️  DESTRUCTIVE EXECUTE: will delete ALL conversations + live_chat_index "
            f"under artifacts/{APP_ID}."
        )

    db = get_firestore_db()
    if not db:
        print("❌ Firestore not initialized. Ensure data/firebase_data.json exists.")
        return

    users_col = db.collection("artifacts").document(APP_ID).collection("users")
    index_coll = db.collection("artifacts").document(APP_ID).collection("live_chat_index")

    # 1) Delete all conversations per user
    users_docs = list(users_col.stream())
    total_convs = 0
    for user_doc in users_docs:
        user_id = user_doc.id
        conv_col = user_doc.reference.collection(conversations_collection)
        conv_docs = list(conv_col.stream())
        count = len(conv_docs)
        total_convs += count
        if count == 0:
            continue
        if dry_run or not execute:
            print(f"  [DRY-RUN] Would delete {count} conversations for user {user_id}")
        else:
            for i in range(0, count, BATCH_SIZE):
                batch = db.batch()
                for conv_doc in conv_docs[i : i + BATCH_SIZE]:
                    batch.delete(conv_doc.reference)
                batch.commit()
            print(f"  Deleted {count} conversations for user {user_id}")

    print(f"\nTotal conversations: {total_convs}")

    # 2) Delete all live_chat_index entries
    index_docs = list(index_coll.stream())
    index_count = len(index_docs)
    if dry_run or not execute:
        print(f"\n  [DRY-RUN] Would delete {index_count} live_chat_index entries")
    else:
        for i in range(0, index_count, BATCH_SIZE):
            batch = db.batch()
            for doc in index_docs[i : i + BATCH_SIZE]:
                batch.delete(doc.reference)
            batch.commit()
        print(f"\n  Deleted {index_count} live_chat_index entries")

    if execute and not dry_run:
        try:
            from services.live_chat_service import live_chat_service

            live_chat_service.invalidate_cache()
            print("\n  Cache invalidated.")
        except Exception as e:
            print(f"\n  ⚠️ Could not invalidate cache: {e}")

    print("\nDone.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete all conversations and live_chat_index (dry-run by default)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Only report, do not delete (default behavior when --execute is omitted)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform deletion (requires typed phrase + allow-env when prod/creds)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=argparse.SUPPRESS,  # legacy flag — never enough alone
    )
    parser.add_argument(
        "--i-understand-delete-all-conversations",
        dest="confirm_phrase",
        metavar="PHRASE",
        default="",
        help=f"Must equal {CONFIRM_PHRASE} to execute",
    )
    return parser


def resolve_mode(args: argparse.Namespace) -> tuple[bool, bool]:
    """Return (dry_run, execute). Default is dry-run; --confirm alone never executes.

    If both --dry-run and --execute are passed, dry-run wins (safer).
    """
    if args.dry_run:
        return (True, False)
    if args.execute:
        return (False, True)
    # Legacy --confirm without --execute: force dry-run and warn via caller.
    return (True, False)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    dry_run, execute = resolve_mode(args)
    if getattr(args, "confirm", False) and not execute:
        print(
            "⚠️  --confirm alone is no longer sufficient. Defaulting to dry-run. "
            "Use --execute with the typed phrase (and allow-env when required)."
        )
    if not execute:
        print("[dry-run default] No deletions will be performed.")
    run_delete(dry_run=dry_run, execute=execute, confirm_phrase=args.confirm_phrase)


if __name__ == "__main__":
    main()
