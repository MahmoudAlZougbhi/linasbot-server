import argparse
import asyncio
from typing import Optional

from services.live_chat_service import live_chat_service
from utils.utils import get_firestore_db


async def _count_index(db) -> int:
    try:
        idx_coll = db.collection("artifacts").document(live_chat_service.APP_ID).collection(live_chat_service.INDEX_COLLECTION)
        current_docs = await asyncio.to_thread(lambda: list(idx_coll.stream()))
        return len(current_docs)
    except Exception as e:
        print(f"⚠️ Could not count current index: {e}")
        return -1


async def main(
    max_users: Optional[int] = None,
    max_conversations_per_user: Optional[int] = None,
    set_conversation_state: bool = True,
    dry_run: bool = False,
):
    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Exiting.")
        return

    before_count = await _count_index(db)
    if before_count >= 0:
        print(f"📊 Existing live_chat_index documents: {before_count}")

    if dry_run:
        print("ℹ️ Dry-run: no writes performed. Use without --dry-run to backfill.")
        return

    summary = await live_chat_service.rebuild_index_from_firestore(
        max_users=max_users,
        max_conversations_per_user=max_conversations_per_user,
        set_conversation_state=set_conversation_state,
        return_details=True,
    )

    written = summary.get("written") if isinstance(summary, dict) else summary
    repaired_states = summary.get("repaired_states") if isinstance(summary, dict) else None
    skipped_missing = summary.get("skipped_missing") if isinstance(summary, dict) else None

    after_count = await _count_index(db)
    delta = after_count - before_count if after_count >= 0 and before_count >= 0 else "?"

    print(f"✅ Backfill complete. Written: {written} Repaired missing states: {repaired_states} Skipped/missing: {skipped_missing}")
    if after_count >= 0:
        print(f"� live_chat_index count after: {after_count} (delta: {delta})")
    if set_conversation_state:
        print("🛡️ conversation_state backfill is enabled: only missing conversation_state fields are filled; existing values are left intact.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="One-time/manual rebuild of live_chat_index from Firestore conversations")
    parser.add_argument("--max-users", type=int, default=None, help="Limit number of users to process")
    parser.add_argument("--max-conversations-per-user", type=int, default=None, help="Limit conversations per user")
    parser.add_argument(
        "--no-state-backfill",
        action="store_true",
        help="Disable filling missing conversation_state fields in source conversations",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show counts without writing to live_chat_index")

    args = parser.parse_args()

    asyncio.run(
        main(
            max_users=args.max_users,
            max_conversations_per_user=args.max_conversations_per_user,
            set_conversation_state=not args.no_state_backfill,
            dry_run=args.dry_run,
        )
    )
