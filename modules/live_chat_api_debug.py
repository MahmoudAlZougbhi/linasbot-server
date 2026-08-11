"""Live Chat status/debug/rebuild endpoints (LOC split from live_chat_api)."""

from __future__ import annotations

from typing import Any

from fastapi import Query

from modules.core import app
from modules.live_chat_api_helpers import _run_endpoint
from services.live_chat_service import live_chat_service


@app.get("/api/live-chat/status")
async def live_chat_status() -> Any:
    """Quick status: index count, users count. If index empty but users exist, call rebuild-index."""
    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        if not db:
            return {"success": False, "error": "Firestore not available", "index_count": 0, "users_count": 0}
        app_id = "linas-ai-bot-backend"
        idx_coll = db.collection("artifacts").document(app_id).collection("live_chat_index")
        users_coll = db.collection("artifacts").document(app_id).collection("users")
        index_docs = list(idx_coll.limit(1000).stream())
        users_docs = list(users_coll.limit(1000).stream())
        index_count = len(index_docs)
        users_count = len(users_docs)
        suggestion = None
        if users_count > 0 and index_count == 0:
            suggestion = "Call POST /api/live-chat/rebuild-index to populate from Firestore conversations"
        return {
            "success": True,
            "index_count": index_count,
            "users_count": users_count,
            "suggestion": suggestion,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "index_count": 0, "users_count": 0}


@app.get("/api/live-chat/debug-firestore")
async def debug_firestore() -> Any:
    """Debug endpoint to check Firestore data without cache"""
    try:
        import datetime

        import config
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        if not db:
            return {"success": False, "error": "Firestore not available"}

        app_id = "linas-ai-bot-backend"
        users_collection = db.collection("artifacts").document(app_id).collection("users")

        users_docs = list(users_collection.stream())
        users_data = []

        for user_doc in users_docs:
            user_id = user_doc.id
            conversations_collection = users_collection.document(user_id).collection(
                config.FIRESTORE_CONVERSATIONS_COLLECTION
            )
            conversations_docs = list(conversations_collection.stream())

            conversations_info = []
            for conv_doc in conversations_docs:
                conv_data = conv_doc.to_dict()
                messages = conv_data.get("messages", [])
                status = conv_data.get("status", "active")
                conv_state = conv_data.get("conversation_state")

                last_message_time = None
                hours_ago = None
                if messages:
                    last_msg = messages[-1]
                    timestamp = last_msg.get("timestamp")
                    if timestamp:
                        if isinstance(timestamp, str):
                            try:
                                last_message_time = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            except Exception:
                                pass
                        elif hasattr(timestamp, "timestamp"):
                            last_message_time = timestamp

                        if last_message_time:
                            try:
                                # Try to calculate hours ago, handle timezone issues
                                now = datetime.datetime.now()
                                # Convert both to naive datetimes to avoid timezone issues
                                if hasattr(last_message_time, "replace") and hasattr(last_message_time, "tzinfo"):
                                    if last_message_time.tzinfo:
                                        last_message_time = last_message_time.replace(tzinfo=None)
                                hours_ago = (now - last_message_time).total_seconds() / 3600
                            except Exception as e:
                                print(f"Error calculating hours_ago: {e}")
                                hours_ago = None

                conversations_info.append(
                    {
                        "id": conv_doc.id,
                        "message_count": len(messages),
                        "status": status,
                        "conversation_state": conv_state,
                        "hours_ago": round(hours_ago, 1) if hours_ago else None,
                        "human_takeover": conv_data.get("human_takeover_active", False),
                    }
                )

            # Lookup live_chat_index doc for this user_id for quick parity check
            index_doc = db.collection("artifacts").document(app_id).collection("live_chat_index")
            idx_docs = list(index_doc.where("user_id", "==", user_id).limit(5).stream())
            index_entries = []
            for idx in idx_docs:
                data = idx.to_dict() or {}
                index_entries.append(
                    {
                        "conversation_id": idx.id,
                        "state": data.get("conversation_state"),
                        "last_message_at": str(data.get("last_message_at")),
                        "last_message_text": data.get("last_message_text"),
                        "unread_count": data.get("unread_count", 0),
                    }
                )

            users_data.append(
                {
                    "user_id": user_id,
                    "conversation_count": len(conversations_docs),
                    "conversations": conversations_info,
                    "index_entries": index_entries,
                }
            )

        return {"success": True, "total_users": len(users_docs), "users": users_data}
    except Exception as e:
        print(f"❌ Error in debug_firestore: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/live-chat/rebuild-index")
async def rebuild_live_chat_index(
    max_users: int = Query(default=None), max_conversations_per_user: int = Query(default=None)
) -> Any:
    """Temporary debug endpoint to rebuild/backfill live_chat_index from Firestore conversations."""

    async def _handler() -> Any:
        written = await live_chat_service.rebuild_index_from_firestore(
            max_users=max_users,
            max_conversations_per_user=max_conversations_per_user,
            set_conversation_state=True,
        )
        return {"success": True, "written": written}

    return await _run_endpoint(_handler)
