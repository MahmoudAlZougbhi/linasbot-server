#!/usr/bin/env python3
"""
Migration: Backfill normalized_phone on users and merge duplicate users/conversations.
Run once after deploying phone normalization + unified identity.

- Backfills user.normalized_phone from phone_full or user_id (using normalize_phone).
- Finds duplicates: different user docs with same normalized_phone.
- Picks canonical user per normalized_phone (prefer has external_id / most messages / newest).
- Merges: copy conversations from duplicate users into canonical user; delete duplicate user docs.

Usage:
  python scripts/migrate_phone_identity.py --dry-run       # report only
  python scripts/migrate_phone_identity.py                 # full migration
  python scripts/migrate_phone_identity.py --skip-backfill # skip Step 1, merge only (faster)
"""
import argparse
import asyncio
import os
import sys

# Project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.phone_utils import normalize_phone, is_phone_like_user_id
from utils.utils import get_firestore_db
import config


APP_ID = "linas-ai-bot-backend"
CONVERSATIONS_COLLECTION = getattr(config, "FIRESTORE_CONVERSATIONS_COLLECTION", "conversations")


def _get_users_collection(db):
    return db.collection("artifacts").document(APP_ID).collection("users")


def _normalized_from_user_doc(user_id: str, user_data: dict) -> str:
    """Derive normalized_phone from user doc."""
    phone_full = user_data.get("phone_full") or ""
    if phone_full and not str(phone_full).startswith("room:"):
        n = normalize_phone(phone_full)
        if n:
            return n
    if is_phone_like_user_id(user_id):
        n = normalize_phone(user_id)
        if n:
            return n
    return ""


def run_migration(dry_run: bool, skip_backfill: bool = False):
    db = get_firestore_db()
    if not db:
        print("❌ Firestore not initialized. Ensure data/firebase_data.json exists.")
        return

    users_col = _get_users_collection(db)
    users_docs = list(users_col.stream())

    # 1) Backfill normalized_phone (skip if --skip-backfill)
    if skip_backfill:
        print("Step 1: Skipped (--skip-backfill)")
    else:
        print("Step 1: Backfill normalized_phone on user docs")
        for doc in users_docs:
            user_id = doc.id
            data = doc.to_dict() or {}
            normalized = _normalized_from_user_doc(user_id, data)
            if normalized and data.get("normalized_phone") != normalized:
                if not dry_run:
                    doc.reference.update({"normalized_phone": normalized})
                print(f"  Backfill {user_id} -> normalized_phone={normalized}")
            elif normalized:
                print(f"  Skip (already set) {user_id} -> {normalized}")

    # 2) Group by normalized_phone to find duplicates
    by_normalized = {}
    for doc in users_docs:
        user_id = doc.id
        data = doc.to_dict() or {}
        norm = data.get("normalized_phone") or _normalized_from_user_doc(user_id, data)
        if not norm:
            continue
        if norm not in by_normalized:
            by_normalized[norm] = []
        by_normalized[norm].append((user_id, data, doc.reference))

    duplicates = {k: v for k, v in by_normalized.items() if len(v) > 1}
    if not duplicates:
        print("\nStep 2: No duplicate users (same normalized_phone) found.")
        return

    print(f"\nStep 2: Found {len(duplicates)} normalized_phones with multiple user docs")
    for norm, group in duplicates.items():
        print(f"  {norm}: {[u[0] for u in group]}")

    # 3) For each group, pick canonical and merge
    print("\nStep 3: Merge duplicates into canonical user")
    for normalized_phone, group in duplicates.items():
        # Prefer: E.164 format (e.g. +961...), then has external_id, then most messages, then newest
        def key(item):
            user_id, data, _ = item
            convs_ref = users_col.document(user_id).collection(CONVERSATIONS_COLLECTION)
            conv_count = len(list(convs_ref.stream()))
            has_ext = 1 if data.get("external_id") else 0
            last = (data.get("last_activity") or data.get("created_at") or "").__str__()
            is_e164 = 1 if (str(user_id).startswith("+") and user_id == normalized_phone) else 0
            return (is_e164, has_ext, conv_count, last)

        ordered = sorted(group, key=key, reverse=True)
        canonical_user_id, canonical_data, canonical_ref = ordered[0]
        duplicates_to_merge = ordered[1:]

        print(f"  Canonical for {normalized_phone}: {canonical_user_id} (rest: {[u[0] for u in duplicates_to_merge]})")

        index_coll = db.collection("artifacts").document(APP_ID).collection("live_chat_index")
        for dup_user_id, dup_data, dup_ref in duplicates_to_merge:
            dup_conv_col = dup_ref.collection(CONVERSATIONS_COLLECTION)
            conv_docs = list(dup_conv_col.stream())
            canonical_conv_col = canonical_ref.collection(CONVERSATIONS_COLLECTION)
            for conv_doc in conv_docs:
                conv_data = conv_doc.to_dict() or {}
                if dry_run:
                    print(f"    [DRY-RUN] Would move conversation {conv_doc.id} from {dup_user_id} to {canonical_user_id}")
                    continue
                # Move conversation preserving ID (so live_chat_index stays valid)
                canonical_conv_col.document(conv_doc.id).set(conv_data)
                conv_doc.reference.delete()
                # Update live_chat_index user_id so UI shows one user
                idx_ref = index_coll.document(conv_doc.id)
                if idx_ref.get().exists:
                    idx_ref.update({"user_id": canonical_user_id})
            if not dry_run:
                dup_ref.delete()
                print(f"    Merged and deleted user {dup_user_id}")

    if not dry_run and duplicates:
        try:
            from services.live_chat_service import live_chat_service
            live_chat_service.invalidate_cache()
            print("\n  Cache invalidated - Live Chat will show merged data on next refresh.")
        except Exception as e:
            print(f"\n  ⚠️ Could not invalidate cache: {e}")

    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(description="Backfill normalized_phone and merge duplicate users")
    parser.add_argument("--dry-run", action="store_true", help="Only report, do not write")
    parser.add_argument("--skip-backfill", action="store_true", help="Skip Step 1, go straight to merge (faster)")
    args = parser.parse_args()
    run_migration(dry_run=args.dry_run, skip_backfill=args.skip_backfill)


if __name__ == "__main__":
    main()
