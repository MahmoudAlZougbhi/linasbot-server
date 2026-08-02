#!/usr/bin/env python3
"""
Ops Live Chat index backfill (explicit, idempotent).

Normal HTTP list/waiting-queue paths NEVER call this — operators run it explicitly.

Features:
  --dry-run          Enumerate planned work without writes
  --resume-from      Resume after a prior user_id
  --checkpoint-file  Persist last completed user_id for safe resume
  --max-users / --max-conversations-per-user
  Progress + failure reporting (no secrets)

Do NOT run against production without owner approval.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from google.cloud import firestore

import config
from services.live_chat_service import live_chat_service
from utils.utils import get_firestore_db


async def _count_index(db: Any) -> int:
    try:
        idx_coll = (
            db.collection("artifacts").document(live_chat_service.APP_ID).collection(live_chat_service.INDEX_COLLECTION)
        )
        current_docs = await asyncio.to_thread(lambda: list(idx_coll.stream()))
        return len(current_docs)
    except Exception as e:
        print(f"WARNING: Could not count current index: {type(e).__name__}")
        return -1


def _load_checkpoint(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("last_user_id") or "") or None
    except Exception:
        return None


def _save_checkpoint(path: Path | None, user_id: str, stats: dict[str, Any]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"last_user_id": user_id, "stats": stats, "updated_at": time.time()}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def _list_user_ids(*, max_users: int | None, resume_from: str | None) -> list[str]:
    users_collection = live_chat_service._get_users_collection()
    if users_collection is None:
        raise RuntimeError("Users collection unavailable")
    docs = await live_chat_service._stream_user_docs(users_collection, limit=None)
    user_ids = [doc.id for doc in docs]
    if resume_from:
        try:
            idx = user_ids.index(resume_from)
            user_ids = user_ids[idx + 1 :]
        except ValueError:
            print("WARNING: resume-from user_id not found; starting from beginning")
    if max_users is not None:
        user_ids = user_ids[: max(0, int(max_users))]
    return user_ids


async def _conversations_for_user(
    users_collection: Any,
    user_id: str,
    max_conversations_per_user: int | None,
) -> list[Any]:
    conversations_collection = users_collection.document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
    q = conversations_collection.order_by("last_updated", direction=firestore.Query.DESCENDING)
    if max_conversations_per_user:
        q = q.limit(max_conversations_per_user)
    return await asyncio.to_thread(lambda: list(q.stream()))


async def run_backfill(
    *,
    max_users: int | None,
    max_conversations_per_user: int | None,
    set_conversation_state: bool,
    dry_run: bool,
    resume_from: str | None,
    checkpoint_file: Path | None,
) -> dict[str, Any]:
    db = get_firestore_db()
    if not db:
        raise RuntimeError("Firestore not initialized")

    before_count = await _count_index(db)
    resume = resume_from or _load_checkpoint(checkpoint_file)
    user_ids = await _list_user_ids(max_users=max_users, resume_from=resume)
    users_collection = live_chat_service._get_users_collection()

    stats: dict[str, Any] = {
        "dry_run": dry_run,
        "users_planned": len(user_ids),
        "users_processed": 0,
        "conversations_seen": 0,
        "written": 0,
        "repaired_states": 0,
        "skipped_missing": 0,
        "failures": [],
        "index_count_before": before_count,
        "resume_from": resume,
    }

    print(
        f"INFO: live_chat_index backfill planned users={len(user_ids)} "
        f"dry_run={dry_run} resume_from={resume!r} index_before={before_count}"
    )

    for user_id in user_ids:
        try:
            conv_docs = await _conversations_for_user(users_collection, user_id, max_conversations_per_user)
        except Exception as e:
            stats["failures"].append({"user_id": user_id, "error": type(e).__name__})
            continue

        stats["conversations_seen"] += len(conv_docs)
        if not dry_run:
            for conv_doc in conv_docs:
                try:
                    result = await live_chat_service._sync_index_from_source(
                        user_id,
                        conv_doc.id,
                        allow_state_backfill=set_conversation_state,
                    )
                    if result.get("written"):
                        stats["written"] += 1
                        if result.get("state_backfill"):
                            stats["repaired_states"] += 1
                    else:
                        stats["skipped_missing"] += 1
                except Exception as e:
                    stats["failures"].append(
                        {
                            "user_id": user_id,
                            "conversation_id": conv_doc.id,
                            "error": type(e).__name__,
                        }
                    )
        stats["users_processed"] += 1
        _save_checkpoint(checkpoint_file, user_id, stats)
        if stats["users_processed"] % 25 == 0:
            print(
                f"PROGRESS: users={stats['users_processed']}/{len(user_ids)} "
                f"written={stats['written']} skipped={stats['skipped_missing']} "
                f"failures={len(stats['failures'])}"
            )

    after_count = await _count_index(db)
    stats["index_count_after"] = after_count
    if before_count >= 0 and after_count >= 0:
        stats["index_delta"] = after_count - before_count

    label = "DRY-RUN complete" if dry_run else "COMPLETE"
    print(
        f"{label}: users={stats['users_processed']} conversations_seen={stats['conversations_seen']} "
        f"written={stats['written']} repaired_states={stats['repaired_states']} "
        f"skipped={stats['skipped_missing']} failures={len(stats['failures'])} "
        f"index_after={after_count}"
    )
    if dry_run:
        print("INFO: No writes performed. Re-run without --dry-run to apply.")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotent rebuild of live_chat_index (dry-run, resume, progress)")
    parser.add_argument("--max-users", type=int, default=None)
    parser.add_argument("--max-conversations-per-user", type=int, default=None)
    parser.add_argument(
        "--no-state-backfill",
        action="store_true",
        help="Do not fill missing conversation_state fields on source docs",
    )
    parser.add_argument("--dry-run", action="store_true", help="Enumerate work without writing index")
    parser.add_argument("--resume-from", type=str, default=None, help="Skip users up to and including this id")
    parser.add_argument(
        "--checkpoint-file",
        type=str,
        default=None,
        help="JSON file storing last completed user_id for safe resume",
    )
    args = parser.parse_args()
    checkpoint = Path(args.checkpoint_file) if args.checkpoint_file else None
    try:
        asyncio.run(
            run_backfill(
                max_users=args.max_users,
                max_conversations_per_user=args.max_conversations_per_user,
                set_conversation_state=not args.no_state_backfill,
                dry_run=args.dry_run,
                resume_from=args.resume_from,
                checkpoint_file=checkpoint,
            )
        )
        return 0
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
