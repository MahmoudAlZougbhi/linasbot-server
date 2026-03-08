import asyncio
from typing import Optional

from services.live_chat_service import live_chat_service
from utils.utils import get_firestore_db


async def main(max_users: Optional[int] = None, max_conversations_per_user: Optional[int] = None):
    db = get_firestore_db()
    if not db:
        print("⚠️ Firestore not initialized. Exiting.")
        return

    # Show current index count
    try:
        idx_coll = db.collection("artifacts").document(live_chat_service.APP_ID).collection(live_chat_service.INDEX_COLLECTION)
        current_docs = await asyncio.to_thread(lambda: list(idx_coll.stream()))
        print(f"📊 Existing live_chat_index documents: {len(current_docs)}")
    except Exception as e:
        print(f"⚠️ Could not count current index: {e}")

    written = await live_chat_service.rebuild_index_from_firestore(
        max_users=max_users,
        max_conversations_per_user=max_conversations_per_user,
        set_conversation_state=True,
    )
    print(f"✅ Backfill complete. Entries written: {written}")


if __name__ == "__main__":
    asyncio.run(main())
