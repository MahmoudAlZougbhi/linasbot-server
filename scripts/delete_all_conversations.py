#!/usr/bin/env python3
"""
Delete ALL conversations and live_chat_index from Firestore. Use to start fresh.

WARNING: This is destructive. User docs (names, gender, etc.) are kept; only
conversations and index entries are deleted.

Usage:
  python scripts/delete_all_conversations.py --dry-run     # report only
  python scripts/delete_all_conversations.py --confirm    # actually delete
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.utils import get_firestore_db

APP_ID = "linas-ai-bot-backend"
CONVERSATIONS_COLLECTION = getattr(config, "FIRESTORE_CONVERSATIONS_COLLECTION", "conversations")
BATCH_SIZE = 500


def _get_users_collection(db: Any) -> Any:
    return db.collection("artifacts").document(APP_ID).collection("users")


def _get_index_collection(db: Any) -> Any:
    return db.collection("artifacts").document(APP_ID).collection("live_chat_index")


def run_delete(dry_run: bool, confirm: bool) -> None:
    db = get_firestore_db()
    if not db:
        print("❌ Firestore not initialized. Ensure data/firebase_data.json exists.")
        return

    if not dry_run and not confirm:
        print("❌ Use --confirm to actually delete. Use --dry-run to preview.")
        return

    users_col = _get_users_collection(db)
    index_coll = _get_index_collection(db)

    # 1) Delete all conversations per user
    users_docs = list(users_col.stream())
    total_convs = 0
    for user_doc in users_docs:
        user_id = user_doc.id
        conv_col = user_doc.reference.collection(CONVERSATIONS_COLLECTION)
        conv_docs = list(conv_col.stream())
        count = len(conv_docs)
        total_convs += count
        if count == 0:
            continue
        if dry_run:
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
    if dry_run:
        print(f"\n  [DRY-RUN] Would delete {index_count} live_chat_index entries")
    else:
        for i in range(0, index_count, BATCH_SIZE):
            batch = db.batch()
            for doc in index_docs[i : i + BATCH_SIZE]:
                batch.delete(doc.reference)
            batch.commit()
        print(f"\n  Deleted {index_count} live_chat_index entries")

    if not dry_run:
        try:
            from services.live_chat_service import live_chat_service

            live_chat_service.invalidate_cache()
            print("\n  Cache invalidated.")
        except Exception as e:
            print(f"\n  ⚠️ Could not invalidate cache: {e}")

    print("\nDone.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete all conversations and live_chat_index")
    parser.add_argument("--dry-run", action="store_true", help="Only report, do not delete")
    parser.add_argument("--confirm", action="store_true", help="Actually perform deletion")
    args = parser.parse_args()
    run_delete(dry_run=args.dry_run, confirm=args.confirm)


if __name__ == "__main__":
    main()
