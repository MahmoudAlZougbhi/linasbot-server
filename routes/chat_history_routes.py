# -*- coding: utf-8 -*-
"""
Chat History API Routes
"""
from fastapi import APIRouter
import datetime
import time
import config

router = APIRouter()

# In-memory cache for customers list (5 minute TTL)
_customers_cache = None
_customers_cache_time = 0
CACHE_TTL = 300  # 5 minutes

@router.get("/api/chat-history/customers")
async def get_chat_history_customers():
    """Get list of all customers with their latest conversation info"""
    global _customers_cache, _customers_cache_time

    # Return cached data if fresh (instant response)
    if _customers_cache and (time.time() - _customers_cache_time) < CACHE_TTL:
        return _customers_cache

    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        if not db:
            return {"success": False, "error": "Firestore not initialized"}

        app_id_for_firestore = "linas-ai-bot-backend"
        users_collection = db.collection("artifacts").document(app_id_for_firestore).collection("users")

        customers = []
        users_docs = list(users_collection.stream())

        for user_doc in users_docs:
            user_id = user_doc.id
            user_data = user_doc.to_dict()

            conversations_collection = users_collection.document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
            conversations_docs = list(conversations_collection.stream())

            if conversations_docs:
                latest_conversation = None
                latest_timestamp = None
                total_messages = 0

                for conv_doc in conversations_docs:
                    conv_data = conv_doc.to_dict()
                    messages = conv_data.get("messages", [])
                    total_messages += len(messages)

                    if messages:
                        last_message = messages[-1]
                        message_timestamp = last_message.get("timestamp")

                        if isinstance(message_timestamp, str):
                            try:
                                message_timestamp = datetime.datetime.fromisoformat(message_timestamp.replace('Z', '+00:00'))
                            except:
                                message_timestamp = datetime.datetime.now()
                        elif hasattr(message_timestamp, 'timestamp'):
                            message_timestamp = datetime.datetime.fromtimestamp(message_timestamp.timestamp())
                        elif hasattr(message_timestamp, 'seconds'):
                            message_timestamp = datetime.datetime.fromtimestamp(message_timestamp.seconds)
                        else:
                            message_timestamp = datetime.datetime.now()

                        if latest_timestamp is None or message_timestamp > latest_timestamp:
                            latest_timestamp = message_timestamp
                            latest_conversation = conv_data

                if latest_conversation:
                    last_message_text = ""
                    if latest_conversation.get("messages"):
                        last_message_text = latest_conversation["messages"][-1].get("text", "")

                    customer_info = latest_conversation.get("customer_info", {})
                    customer_name = customer_info.get("name", "Unknown Customer")
                    phone_full = customer_info.get("phone_full", user_id)
                    phone_clean = customer_info.get("phone_clean", user_id.replace("+", ""))

                    if customer_name == "Unknown Customer":
                        customer_name = config.user_names.get(user_id, "Unknown Customer")

                    customer_data = {
                        "user_id": user_id,
                        "user_name": customer_name,
                        "phone_full": phone_full,
                        "phone_clean": phone_clean,
                        "last_message": last_message_text,
                        "last_message_time": latest_timestamp.isoformat() if latest_timestamp else None,
                        "message_count": total_messages,
                        "conversation_count": len(conversations_docs),
                        "unread_count": 0
                    }
                    customers.append(customer_data)

        customers.sort(key=lambda x: x["last_message_time"] or "", reverse=True)

        # Cache the result for fast subsequent loads
        result = {
            "success": True,
            "customers": customers,
            "total_customers": len(customers)
        }
        _customers_cache = result
        _customers_cache_time = time.time()

        return result
        
    except Exception as e:
        print(f"❌ Error getting chat history customers: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/api/chat-history/refresh")
async def refresh_chat_history_cache():
    """Force refresh the customers cache"""
    global _customers_cache, _customers_cache_time
    _customers_cache = None
    _customers_cache_time = 0
    return await get_chat_history_customers()


@router.get("/api/chat-history/conversations/{user_id}")
async def get_customer_conversations(user_id: str):
    """Get all conversations for a specific customer"""
    try:
        from utils.utils import get_firestore_db
        
        db = get_firestore_db()
        if not db:
            return {"success": False, "error": "Firestore not initialized"}
        
        app_id_for_firestore = "linas-ai-bot-backend"
        conversations_collection = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
        
        conversations = []
        docs = list(conversations_collection.stream())
        
        for doc in docs:
            doc_data = doc.to_dict()
            messages = doc_data.get("messages", [])
            
            for message in messages:
                timestamp = message.get("timestamp")
                if isinstance(timestamp, str):
                    try:
                        message["timestamp"] = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00')).isoformat()
                    except:
                        message["timestamp"] = datetime.datetime.now().isoformat()
                elif hasattr(timestamp, 'timestamp'):
                    message["timestamp"] = datetime.datetime.fromtimestamp(timestamp.timestamp()).isoformat()
                elif hasattr(timestamp, 'seconds'):
                    message["timestamp"] = datetime.datetime.fromtimestamp(timestamp.seconds).isoformat()
                else:
                    message["timestamp"] = datetime.datetime.now().isoformat()
            
            conversations.append({
                "id": doc.id,
                "messages": messages,
                "timestamp": doc_data.get("timestamp"),
                "user_id": doc_data.get("user_id"),
                "sentiment": doc_data.get("sentiment", "neutral"),
                "human_takeover_active": doc_data.get("human_takeover_active", False),
                "status": doc_data.get("status", "active")
            })
        
        conversations.sort(key=lambda x: x.get("timestamp") or "", reverse=False)
        
        return {
            "success": True,
            "conversations": conversations,
            "user_id": user_id,
            "total_conversations": len(conversations),
            "total_messages": sum(len(conv.get("messages", [])) for conv in conversations)
        }
        
    except Exception as e:
        print(f"❌ Error getting conversations for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }
