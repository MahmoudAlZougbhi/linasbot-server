# -*- coding: utf-8 -*-
"""
Live Chat Service - Hybrid Approach
- 6-hour time filter for active conversations
- Groups conversations by client (one card per client)
- Status management: active, resolved, archived
- Auto-reopen on new message
"""

import datetime
import asyncio
import json
import os
import re
from typing import List, Dict, Optional, Any, Tuple
from collections import defaultdict
from google.cloud import firestore
import config
from utils.utils import get_firestore_db, set_human_takeover_status
from services.media_service import build_whatsapp_audio_delivery_url


class LiveChatService:
    """Service for managing live chat operations with hybrid approach"""

    # Time window for active conversations (6 hours in seconds)
    ACTIVE_TIME_WINDOW = 6 * 60 * 60  # 6 hours

    # Cache configuration
    CACHE_TTL = 5  # seconds - short cache for near real-time updates
    PHONE_MAPPING_CACHE_TTL = 60  # seconds

    def __init__(self):
        self.operator_sessions = {}
        self.operator_status = defaultdict(lambda: "available")
        # Cache for active conversations
        self._conversations_cache = None
        self._conversations_cache_time = None
        # Cache for waiting queue
        self._queue_cache = None
        self._queue_cache_time = None
        # Cache for static phone<->room mapping file
        self._phone_to_room_cache = {}
        self._room_to_phone_cache = {}
        self._phone_mapping_cache_time = None

    def invalidate_cache(self):
        """Clear service caches so UI reads latest state."""
        self._conversations_cache = None
        self._conversations_cache_time = None
        self._queue_cache = None
        self._queue_cache_time = None

    def _dedupe_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        De-duplicate messages for idempotent read paths.
        Uses source_message_id when available, otherwise falls back to a content signature.
        """
        if not messages:
            return []

        deduped: List[Dict[str, Any]] = []
        seen_source_ids = set()
        seen_signatures = set()

        for msg in messages:
            metadata = msg.get("metadata", {}) or {}
            source_message_id = str(metadata.get("source_message_id", "")).strip()

            if source_message_id:
                if source_message_id in seen_source_ids:
                    continue
                seen_source_ids.add(source_message_id)

            msg_role = str(msg.get("role", "")).strip().lower()
            msg_type = str(msg.get("type") or metadata.get("type") or "text").strip().lower()
            msg_text = str(msg.get("text", "")).strip()
            msg_ts = self._parse_timestamp(msg.get("timestamp")).replace(microsecond=0).isoformat()
            signature = (msg_role, msg_type, msg_text, msg_ts)

            if not source_message_id and signature in seen_signatures:
                continue

            seen_signatures.add(signature)
            deduped.append(msg)

        return deduped

    def _history_filter_match(self, dt: datetime.datetime, filter_by: str) -> bool:
        if filter_by == "all":
            return True

        now = datetime.datetime.now(datetime.timezone.utc)
        age_hours = (now - dt).total_seconds() / 3600.0

        if filter_by == "today":
            return age_hours <= 24
        if filter_by == "week":
            return age_hours <= 24 * 7
        if filter_by == "month":
            return age_hours <= 24 * 30
        return True

    def _paginate(self, items: List[Dict[str, Any]], page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int, int]:
        safe_page = max(1, int(page))
        safe_page_size = max(1, min(int(page_size), 1000))
        total_items = len(items)
        total_pages = max(1, (total_items + safe_page_size - 1) // safe_page_size)
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        return items[start:end], total_items, total_pages
        
    async def get_active_conversations(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get active conversations grouped by client
        - Only shows conversations from last 6 hours
        - Groups multiple conversations per client
        - Excludes resolved/archived conversations
        - Returns one entry per client with their latest conversation
        - Optional search by client name or phone (partial, normalized)
        """
        normalized_search = (search or "").strip()

        # Check cache first
        current_time = datetime.datetime.now(datetime.timezone.utc)
        if (self._conversations_cache is not None and
            self._conversations_cache_time is not None and
            (current_time - self._conversations_cache_time).total_seconds() < self.CACHE_TTL):
            print(f"📦 Returning cached active conversations ({len(self._conversations_cache)} clients)")
            if normalized_search:
                filtered_cached = self._filter_conversations(self._conversations_cache, normalized_search)
                print(f"🔎 Live chat search '{normalized_search}': {len(filtered_cached)} matches (cache)")
                return filtered_cached
            return self._conversations_cache

        try:
            db = get_firestore_db()
            if not db:
                return []
            
            app_id = "linas-ai-bot-backend"
            users_collection = db.collection("artifacts").document(app_id).collection("users")
            
            # Dictionary to group conversations by client
            client_conversations = {}
            current_time = datetime.datetime.now(datetime.timezone.utc)

            # Pull all users (no hard cap) so live/history stay consistent.
            # Try sorted query first; fallback if ordering field is inconsistent.
            try:
                users_docs = await asyncio.to_thread(
                    lambda: list(users_collection.order_by("last_activity", direction=firestore.Query.DESCENDING).stream())
                )
            except Exception:
                users_docs = await asyncio.to_thread(lambda: list(users_collection.stream()))

            # Helper function to fetch conversations for a single user
            async def fetch_user_conversations(user_id):
                """Fetch all conversations for a user"""
                try:
                    conversations_collection = users_collection.document(user_id).collection(
                        config.FIRESTORE_CONVERSATIONS_COLLECTION
                    )
                    # ✅ Use asyncio.to_thread to prevent blocking the event loop
                    conversations_docs = await asyncio.to_thread(lambda: list(conversations_collection.stream()))
                    return (user_id, conversations_docs)
                except Exception as e:
                    print(f"⚠️ Error fetching conversations for user {user_id}: {e}")
                    return (user_id, [])

            # Fetch conversations for all users in parallel
            user_ids = [doc.id for doc in users_docs]
            conversation_results = await asyncio.gather(
                *[fetch_user_conversations(uid) for uid in user_ids],
                return_exceptions=True
            )

            # Process results
            for result in conversation_results:
                if isinstance(result, Exception):
                    print(f"⚠️ Error in parallel fetch: {result}")
                    continue

                user_id, conversations_docs = result

                # Collect all conversations for this client
                client_convs = []
                for conv_doc in conversations_docs:
                    conv_data = conv_doc.to_dict()
                    messages = self._dedupe_messages(conv_data.get("messages", []))

                    if not messages:
                        continue

                    # Get conversation status
                    conv_status = conv_data.get("status", "active")

                    # Skip resolved or archived conversations
                    if conv_status in ["resolved", "archived"]:
                        continue

                    # Get last message time (use actual last message for timing)
                    last_message = messages[-1]
                    last_message_time = self._parse_timestamp(last_message.get("timestamp"))

                    # For preview, find the last non-smart message
                    last_preview_message = last_message
                    for msg in reversed(messages):
                        if msg.get("metadata", {}).get("source") != "smart_message":
                            last_preview_message = msg
                            break

                    # Apply time filter (read-only; do not mutate status while listing)
                    time_diff = (current_time - last_message_time).total_seconds()
                    if time_diff > self.ACTIVE_TIME_WINDOW:
                        # Keep human/waiting conversations visible even if old.
                        if not conv_data.get("human_takeover_active", False):
                            continue
                    
                    # Get conversation metadata
                    human_takeover = conv_data.get("human_takeover_active", False)
                    operator_id = conv_data.get("operator_id")
                    sentiment = conv_data.get("sentiment", "neutral")
                    
                    # Determine status
                    if human_takeover:
                        status = "human" if operator_id else "waiting_human"
                    else:
                        status = "bot"
                    
                    # Skip conversations waiting for human - they should only appear in waiting queue
                    if status == "waiting_human":
                        continue
                    
                    # Calculate duration
                    first_message_time = self._parse_timestamp(messages[0].get("timestamp"))
                    duration_seconds = int((last_message_time - first_message_time).total_seconds())
                    
                    conversation = {
                        "conversation_id": conv_doc.id,
                        "user_id": user_id,
                        "status": status,
                        "message_count": len(messages),
                        "last_activity": last_message_time.isoformat(),
                        "last_activity_dt": last_message_time,
                        "duration_seconds": duration_seconds,
                        "sentiment": sentiment,
                        "operator_id": operator_id,
                        "customer_info": conv_data.get("customer_info", {}),
                        "last_message": {
                            "content": last_preview_message.get("text", ""),
                            "is_user": last_preview_message.get("role") == "user",
                            "timestamp": last_message_time.isoformat()
                        }
                    }
                    
                    client_convs.append(conversation)
                
                # If client has conversations, group them
                if client_convs:
                    # Sort by last activity (most recent first)
                    client_convs.sort(key=lambda x: x["last_activity_dt"], reverse=True)
                    
                    # Get latest conversation
                    latest_conv = client_convs[0]
                    
                    # Get user info from latest conversation snapshot.
                    customer_info = latest_conv.get("customer_info", {}) or {}
                    user_name = customer_info.get("name") or config.user_names.get(user_id, "Unknown Customer")
                    phone_full, phone_clean = self._resolve_user_phone(user_id=user_id, customer_info=customer_info)

                    language = config.user_data_whatsapp.get(user_id, {}).get('user_preferred_lang', 'ar')

                    # Get gender from customer_info or memory
                    gender = customer_info.get("gender") or config.user_gender.get(user_id, "unknown")

                    # Create grouped client entry
                    client_entry = {
                        "user_id": user_id,
                        "user_name": user_name,
                        "user_phone": phone_full,
                        "phone_clean": phone_clean,
                        "language": language,
                        "gender": gender,
                        "conversation_count": len(client_convs),
                        "conversations": client_convs,
                        # Latest conversation details
                        "conversation_id": latest_conv["conversation_id"],
                        "status": latest_conv["status"],
                        "message_count": sum(c["message_count"] for c in client_convs),
                        "last_activity": latest_conv["last_activity"],
                        "duration_seconds": latest_conv["duration_seconds"],
                        "sentiment": latest_conv["sentiment"],
                        "operator_id": latest_conv["operator_id"],
                        "last_message": latest_conv["last_message"]
                    }
                    
                    client_conversations[user_id] = client_entry
            
            # Convert to list and sort by last activity
            active_conversations = list(client_conversations.values())
            active_conversations.sort(key=lambda x: x["last_activity"], reverse=True)

            print(f"📊 Active conversations: {len(active_conversations)} clients (6-hour window)")

            # Update cache
            self._conversations_cache = active_conversations
            self._conversations_cache_time = current_time

            if normalized_search:
                filtered = self._filter_conversations(active_conversations, normalized_search)
                print(f"🔎 Live chat search '{normalized_search}': {len(filtered)} matches")
                return filtered

            return active_conversations
            
        except Exception as e:
            print(f"❌ Error getting active conversations: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_history_customers(
        self,
        search: str = "",
        filter_by: str = "all",
        page: int = 1,
        page_size: int = 200,
    ) -> Dict[str, Any]:
        """Canonical customer list for chat history."""
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

            app_id = "linas-ai-bot-backend"
            users_collection = db.collection("artifacts").document(app_id).collection("users")
            users_docs = await asyncio.to_thread(lambda: list(users_collection.stream()))

            async def fetch_user_conversations(user_doc):
                user_id = user_doc.id
                conversations_collection = users_collection.document(user_id).collection(
                    config.FIRESTORE_CONVERSATIONS_COLLECTION
                )
                conversations_docs = await asyncio.to_thread(lambda: list(conversations_collection.stream()))
                return user_id, conversations_docs

            fetch_results = await asyncio.gather(
                *[fetch_user_conversations(doc) for doc in users_docs],
                return_exceptions=True
            )

            customers: List[Dict[str, Any]] = []
            for result in fetch_results:
                if isinstance(result, Exception):
                    continue

                user_id, conversations_docs = result

                latest_timestamp = None
                latest_message_text = ""
                latest_customer_info = {}
                total_messages = 0
                conversation_count = 0

                for conv_doc in conversations_docs:
                    conversation_count += 1
                    conv_data = conv_doc.to_dict() or {}
                    messages = self._dedupe_messages(conv_data.get("messages", []))
                    if not messages:
                        continue

                    total_messages += len(messages)
                    last_message = messages[-1]
                    candidate_ts = self._parse_timestamp(last_message.get("timestamp"))

                    if latest_timestamp is None or candidate_ts > latest_timestamp:
                        latest_timestamp = candidate_ts
                        latest_message_text = str(last_message.get("text", ""))
                        latest_customer_info = conv_data.get("customer_info", {}) or {}

                if latest_timestamp is None:
                    continue

                user_name = (
                    latest_customer_info.get("name")
                    or config.user_names.get(user_id)
                    or "Unknown Customer"
                )
                phone_full, phone_clean = self._resolve_user_phone(user_id=user_id, customer_info=latest_customer_info)
                gender = latest_customer_info.get("gender") or config.user_gender.get(user_id, "unknown")

                customers.append({
                    "user_id": user_id,
                    "user_name": user_name,
                    "phone_full": phone_full,
                    "phone_clean": phone_clean,
                    "gender": gender,
                    "last_message": latest_message_text,
                    "last_message_time": latest_timestamp.isoformat(),
                    "message_count": total_messages,
                    "conversation_count": conversation_count,
                    "unread_count": 0,
                })

            search_value = (search or "").strip().lower()
            if search_value:
                filtered_customers = []
                for customer in customers:
                    if (
                        search_value in str(customer.get("user_name", "")).lower()
                        or search_value in str(customer.get("user_id", "")).lower()
                        or search_value in str(customer.get("phone_full", "")).lower()
                        or search_value in str(customer.get("phone_clean", "")).lower()
                        or search_value in str(customer.get("last_message", "")).lower()
                    ):
                        filtered_customers.append(customer)
                customers = filtered_customers

            customers = [
                customer for customer in customers
                if self._history_filter_match(
                    self._parse_timestamp(customer.get("last_message_time")),
                    filter_by
                )
            ]

            customers.sort(key=lambda item: item.get("last_message_time", ""), reverse=True)
            paged_customers, total_customers, total_pages = self._paginate(customers, page, page_size)

            return {
                "success": True,
                "customers": paged_customers,
                "total_customers": total_customers,
                "page": max(1, int(page)),
                "page_size": max(1, min(int(page_size), 1000)),
                "total_pages": total_pages,
            }
        except Exception as e:
            print(f"❌ Error getting history customers: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    async def get_history_conversations(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 200,
        status: str = "all",
        search: str = "",
    ) -> Dict[str, Any]:
        """Canonical conversation list for a single user."""
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

            app_id = "linas-ai-bot-backend"
            conversations_collection = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)

            conversations_docs = await asyncio.to_thread(lambda: list(conversations_collection.stream()))

            conversations: List[Dict[str, Any]] = []
            total_messages = 0
            for conv_doc in conversations_docs:
                conv_data = conv_doc.to_dict() or {}
                messages = self._dedupe_messages(conv_data.get("messages", []))
                message_count = len(messages)
                total_messages += message_count

                last_timestamp = self._parse_timestamp(conv_data.get("timestamp"))
                last_message = None
                if messages:
                    raw_last = messages[-1]
                    last_timestamp = self._parse_timestamp(raw_last.get("timestamp"))
                    last_message = {
                        "role": raw_last.get("role"),
                        "text": raw_last.get("text", ""),
                        "timestamp": last_timestamp.isoformat(),
                        "type": raw_last.get("type", "text"),
                    }

                conversations.append({
                    "id": conv_doc.id,
                    "message_count": message_count,
                    "last_message": last_message,
                    "timestamp": last_timestamp.isoformat(),
                    "user_id": conv_data.get("user_id", user_id),
                    "sentiment": conv_data.get("sentiment", "neutral"),
                    "human_takeover_active": conv_data.get("human_takeover_active", False),
                    "status": conv_data.get("status", "active"),
                })

            if status and status != "all":
                conversations = [conv for conv in conversations if conv.get("status") == status]

            search_value = (search or "").strip().lower()
            if search_value:
                conversations = [
                    conv for conv in conversations
                    if search_value in str(conv.get("id", "")).lower()
                    or search_value in str(conv.get("status", "")).lower()
                    or search_value in str((conv.get("last_message") or {}).get("text", "")).lower()
                ]

            conversations.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
            paged_conversations, total_conversations, total_pages = self._paginate(conversations, page, page_size)

            return {
                "success": True,
                "conversations": paged_conversations,
                "user_id": user_id,
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "page": max(1, int(page)),
                "page_size": max(1, min(int(page_size), 1000)),
                "total_pages": total_pages,
            }
        except Exception as e:
            print(f"❌ Error getting history conversations for {user_id}: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    async def get_history_messages(
        self,
        user_id: str,
        conversation_id: str,
        page: int = 1,
        page_size: int = 1000,
        search: str = "",
        sort: str = "asc",
    ) -> Dict[str, Any]:
        """Canonical paginated message history for one conversation."""
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized", "messages": []}

            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(user_id).collection(
                config.FIRESTORE_CONVERSATIONS_COLLECTION
            ).document(conversation_id)

            conv_doc = await asyncio.to_thread(conv_ref.get)
            if not conv_doc.exists:
                return {"success": False, "error": "Conversation not found", "messages": []}

            conv_data = conv_doc.to_dict() or {}
            messages = self._dedupe_messages(conv_data.get("messages", []))
            normalized_messages = []
            for msg in messages:
                normalized_messages.append({
                    **msg,
                    "timestamp": self._parse_timestamp(msg.get("timestamp")).isoformat(),
                })

            search_value = (search or "").strip().lower()
            if search_value:
                normalized_messages = [
                    msg for msg in normalized_messages
                    if search_value in str(msg.get("text", "")).lower()
                ]

            reverse_sort = str(sort).lower() == "desc"
            normalized_messages.sort(key=lambda item: item.get("timestamp", ""), reverse=reverse_sort)
            safe_page = max(1, int(page))
            safe_page_size = max(1, min(int(page_size), 1000))
            total_messages = len(normalized_messages)
            total_pages = max(1, (total_messages + safe_page_size - 1) // safe_page_size)

            # Backward-compatible default: when UI requests page 1 in ascending order,
            # return the latest chunk so recent messages are always visible.
            if (not reverse_sort) and safe_page == 1 and total_messages > safe_page_size:
                paged_messages = normalized_messages[-safe_page_size:]
            else:
                paged_messages, _, _ = self._paginate(normalized_messages, safe_page, safe_page_size)

            return {
                "success": True,
                "conversation_id": conversation_id,
                "messages": paged_messages,
                "total_messages": total_messages,
                "page": safe_page,
                "page_size": safe_page_size,
                "total_pages": total_pages,
                "returned_messages": len(paged_messages),
            }
        except Exception as e:
            print(f"❌ Error getting history messages for {conversation_id}: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e), "messages": []}
    
    async def get_client_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all conversations for a specific client (for expanded view)
        """
        try:
            db = get_firestore_db()
            if not db:
                return []

            app_id = "linas-ai-bot-backend"
            conversations_collection = db.collection("artifacts").document(app_id).collection(
                "users"
            ).document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)

            # ✅ Use asyncio.to_thread to prevent blocking the event loop
            conversations_docs = await asyncio.to_thread(lambda: list(conversations_collection.stream()))
            conversations = []
            
            for conv_doc in conversations_docs:
                conv_data = conv_doc.to_dict()
                messages = self._dedupe_messages(conv_data.get("messages", []))
                
                if not messages:
                    continue
                
                last_message = messages[-1]
                last_message_time = self._parse_timestamp(last_message.get("timestamp"))
                
                conversations.append({
                    "conversation_id": conv_doc.id,
                    "message_count": len(messages),
                    "last_activity": last_message_time.isoformat(),
                    "status": conv_data.get("status", "active"),
                    "sentiment": conv_data.get("sentiment", "neutral"),
                    "human_takeover_active": conv_data.get("human_takeover_active", False),
                    "operator_id": conv_data.get("operator_id")
                })
            
            conversations.sort(key=lambda x: x["last_activity"], reverse=True)
            return conversations
            
        except Exception as e:
            print(f"❌ Error getting client conversations: {e}")
            return []
    
    async def get_waiting_queue(self) -> List[Dict[str, Any]]:
        """
        Get conversations waiting for human intervention
        Queries Firebase directly for conversations with human_takeover_active=True and operator_id=None
        """
        try:
            db = get_firestore_db()
            if not db:
                return []

            app_id = "linas-ai-bot-backend"
            users_collection = db.collection("artifacts").document(app_id).collection("users")

            waiting_queue = []
            current_time = datetime.datetime.now(datetime.timezone.utc)

            # ✅ Use asyncio.to_thread to prevent blocking the event loop
            users_docs = await asyncio.to_thread(lambda: list(users_collection.stream()))

            for user_doc in users_docs:
                user_id = user_doc.id

                conversations_collection = users_collection.document(user_id).collection(
                    config.FIRESTORE_CONVERSATIONS_COLLECTION
                )
                # ✅ Use asyncio.to_thread to prevent blocking the event loop
                conversations_docs = await asyncio.to_thread(lambda: list(conversations_collection.stream()))
                
                for conv_doc in conversations_docs:
                    conv_data = conv_doc.to_dict()
                    messages = self._dedupe_messages(conv_data.get("messages", []))
                    
                    if not messages:
                        continue
                    
                    # Check if conversation is waiting for human
                    human_takeover = conv_data.get("human_takeover_active", False)
                    operator_id = conv_data.get("operator_id")
                    conv_status = conv_data.get("status", "active")
                    
                    # Only include conversations waiting for human (takeover active but no operator assigned)
                    if not (human_takeover and operator_id is None):
                        continue
                    
                    # Skip resolved/archived
                    if conv_status in ["resolved", "archived"]:
                        continue
                    
                    # Get last message time (use actual last message for timing)
                    last_message = messages[-1]
                    last_message_time = self._parse_timestamp(last_message.get("timestamp"))

                    # For preview, find the last non-smart message
                    last_preview_message = last_message
                    for msg in reversed(messages):
                        if msg.get("metadata", {}).get("source") != "smart_message":
                            last_preview_message = msg
                            break

                    # Calculate wait time
                    escalation_time = conv_data.get("escalation_time")
                    if escalation_time:
                        escalation_dt = self._parse_timestamp(escalation_time)
                        wait_time_seconds = int((current_time - escalation_dt).total_seconds())
                    else:
                        wait_time_seconds = int((current_time - last_message_time).total_seconds())
                    
                    # Get user info from Firebase customer_info first, fallback to config
                    customer_info = conv_data.get("customer_info", {})
                    user_name = customer_info.get("name") or config.user_names.get(user_id, "Unknown Customer")
                    phone_full, phone_clean = self._resolve_user_phone(user_id=user_id, customer_info=customer_info)
                    
                    language = config.user_data_whatsapp.get(user_id, {}).get('user_preferred_lang', 'ar')
                    sentiment = conv_data.get("sentiment", "neutral")
                    
                    # Determine reason and priority
                    escalation_reason = conv_data.get("escalation_reason", "user_request")
                    priority = 1 if sentiment == "negative" or wait_time_seconds > 300 else 2
                    
                    queue_item = {
                        "conversation_id": conv_doc.id,
                        "user_id": user_id,
                        "user_name": user_name,
                        "user_phone": phone_full,
                        "phone_clean": phone_clean,
                        "language": language,
                        "reason": escalation_reason,
                        "wait_time_seconds": wait_time_seconds,
                        "sentiment": sentiment,
                        "message_count": len(messages),
                        "priority": priority,
                        "last_message": last_preview_message.get("text", "")
                    }

                    waiting_queue.append(queue_item)
            
            # Sort by priority (1=high, 2=normal) then by wait time (longest first)
            waiting_queue.sort(key=lambda x: (x["priority"], -x["wait_time_seconds"]))
            
            print(f"📊 Waiting queue: {len(waiting_queue)} conversations")
            
            return waiting_queue
            
        except Exception as e:
            print(f"❌ Error getting waiting queue: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def end_conversation(self, conversation_id: str, user_id: str, operator_id: str, adapter=None) -> Dict[str, Any]:
        """
        Mark conversation as resolved/ended
        - Sets status to 'resolved'
        - Records who resolved it and when
        - Removes from active view
        - Sends notification to customer
        - Can be reopened if customer messages again
        """
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}
            
            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
            
            # Update conversation status
            update_data = {
                "status": "resolved",
                "resolved_at": datetime.datetime.now(),
                "resolved_by": operator_id,
                "human_takeover_active": False,
                "operator_id": None
            }
            
            print(f"🔄 Updating conversation {conversation_id} with data: {update_data}")
            # ✅ Use asyncio.to_thread to prevent blocking the event loop
            await asyncio.to_thread(conv_ref.update, update_data)
            print(f"✅ Firebase updated successfully for conversation {conversation_id}")

            # Verify the update
            updated_doc = await asyncio.to_thread(conv_ref.get)
            if updated_doc.exists:
                updated_data = updated_doc.to_dict()
                print(f"✅ Verified: status = {updated_data.get('status')}, resolved_by = {updated_data.get('resolved_by')}")
            
            # Update in-memory state
            config.user_in_human_takeover_mode[user_id] = False
            if conversation_id in self.operator_sessions:
                del self.operator_sessions[conversation_id]

            # Clear current_conversation_id so next message creates a new conversation
            if user_id in config.user_data_whatsapp:
                config.user_data_whatsapp[user_id].pop('current_conversation_id', None)
                print(f"🔄 Cleared current_conversation_id for {user_id} - next message will start new conversation")

            # Invalidate cache
            self.invalidate_cache()

            # Send notification to customer
            if adapter:
                try:
                    # Multilingual end conversation messages
                    end_messages = {
                        "ar": "شكراً لتواصلك معنا! تم إنهاء المحادثة. إذا كان لديك أي استفسار آخر، لا تتردد في مراسلتنا مجدداً. 🌟",
                        "en": "Thank you for contacting us! This conversation has been ended. If you have any other questions, feel free to message us again. 🌟",
                        "fr": "Merci de nous avoir contactés! Cette conversation est terminée. Si vous avez d'autres questions, n'hésitez pas à nous écrire à nouveau. 🌟"
                    }
                    
                    # Get user's preferred language from config
                    user_lang = config.user_data_whatsapp.get(user_id, {}).get('user_preferred_lang', 'ar')
                    notification_message = end_messages.get(user_lang, end_messages['ar'])
                    
                    # Send notification via WhatsApp
                    await adapter.send_text_message(user_id, notification_message)
                    print(f"✅ Sent end conversation notification to customer {user_id}")
                    
                    # Save notification to Firebase
                    from utils.utils import save_conversation_message_to_firestore
                    await save_conversation_message_to_firestore(
                        user_id=user_id,
                        role="ai",
                        text=notification_message,
                        conversation_id=conversation_id,
                        metadata={"type": "end_conversation_notification", "operator_id": operator_id}
                    )
                except Exception as e:
                    print(f"⚠️ Failed to send end conversation notification: {e}")
            
            print(f"✅ Conversation {conversation_id} marked as resolved by {operator_id}")
            
            return {
                "success": True,
                "message": "Conversation ended successfully",
                "conversation_id": conversation_id,
                "status": "resolved"
            }
            
        except Exception as e:
            print(f"❌ Error ending conversation: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    async def reopen_conversation(self, conversation_id: str, user_id: str) -> Dict[str, Any]:
        """
        Reopen a resolved conversation (auto-called when customer messages again)
        """
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}
            
            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
            
            # Reopen conversation - use asyncio.to_thread to prevent blocking
            await asyncio.to_thread(conv_ref.update, {
                "status": "active",
                "reopened_at": datetime.datetime.now(),
                "resolved_at": None,
                "resolved_by": None
            })
            
            print(f"✅ Conversation {conversation_id} reopened (customer messaged again)")
            
            return {
                "success": True,
                "message": "Conversation reopened",
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"❌ Error reopening conversation: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _auto_archive_conversation(self, user_id: str, conversation_id: str):
        """
        Auto-archive conversations older than 6 hours
        """
        try:
            db = get_firestore_db()
            if not db:
                return
            
            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)
            
            # ✅ Use asyncio.to_thread to prevent blocking the event loop
            await asyncio.to_thread(conv_ref.update, {
                "status": "archived",
                "archived_at": datetime.datetime.now(),
                "archived_reason": "auto_6h_timeout"
            })

            print(f"📦 Auto-archived conversation {conversation_id} (6-hour timeout)")
            
        except Exception as e:
            print(f"⚠️ Error auto-archiving conversation: {e}")
    
    async def takeover_conversation(self, conversation_id: str, user_id: str, operator_id: str, operator_name: str = None) -> Dict[str, Any]:
        """Operator takes over a conversation"""
        try:
            await set_human_takeover_status(user_id, conversation_id, True, operator_id, operator_name)
            config.user_in_human_takeover_mode[user_id] = True
            self.operator_sessions[conversation_id] = operator_id

            # Invalidate cache
            self.invalidate_cache()

            print(f"✅ Operator {operator_id} took over conversation {conversation_id}")

            return {
                "success": True,
                "message": "Conversation taken over successfully",
                "conversation_id": conversation_id,
                "operator_id": operator_id
            }
            
        except Exception as e:
            print(f"❌ Error taking over conversation: {e}")
            return {"success": False, "error": str(e)}
    
    async def release_conversation(self, conversation_id: str, user_id: str) -> Dict[str, Any]:
        """Release conversation back to bot"""
        try:
            await set_human_takeover_status(user_id, conversation_id, False)
            config.user_in_human_takeover_mode[user_id] = False
            if conversation_id in self.operator_sessions:
                del self.operator_sessions[conversation_id]

            # Invalidate cache
            self.invalidate_cache()

            print(f"✅ Conversation {conversation_id} released back to bot")

            return {
                "success": True,
                "message": "Conversation released to bot successfully",
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"❌ Error releasing conversation: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_operator_message(
        self, conversation_id: str, user_id: str, message: str, operator_id: str, adapter, message_type: str = "text"
    ) -> Dict[str, Any]:
        """Send message from operator to customer
        
        Args:
            conversation_id: The conversation ID
            user_id: The customer's user ID (room_id for Qiscus)
            message: Message content (text for text, base64 for voice/image)
            operator_id: The operator's ID
            adapter: WhatsApp adapter instance
            message_type: Type of message - "text", "voice", or "image"
        """
        try:
            from utils.utils import save_conversation_message_to_firestore, get_firestore_db
            
            # For Qiscus, we need to fetch the phone_number from Firebase
            phone_number = None
            db = get_firestore_db()
            if db:
                try:
                    app_id = "linas-ai-bot-backend"
                    user_doc = db.collection("artifacts").document(app_id).collection("users").document(user_id).get()
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        phone_number = user_data.get("phone_full")
                        print(f"📱 Found phone_number from Firebase: {phone_number}")
                except Exception as e:
                    print(f"⚠️ Could not fetch phone_number from Firebase: {e}")
            
            # Handle different message types
            if message_type == "voice":
                # message contains base64 audio data
                
                print(f"🎙️ Operator {operator_id} recorded voice message for {user_id}")
                
                # Step 0: Convert WebM to Opus (Qiscus/WhatsApp standard)
                print(f"� Converting voice to Opus format (WhatsApp standard)...")
                audio_data_to_upload = message
                upload_file_name = f"voice_{user_id}_{int(__import__('time').time())}.webm"
                upload_file_type = "audio/webm"
                
                try:
                    from utils.utils import convert_webm_to_opus
                    opus_data, opus_file_name = convert_webm_to_opus(message)
                    if opus_file_name:  # Conversion successful
                        audio_data_to_upload = opus_data
                        upload_file_name = opus_file_name
                        upload_file_type = "audio/ogg"
                        print(f"✅ Voice converted to OGG/Opus")
                except Exception as e:
                    print(f"⚠️ WebM to Opus conversion failed: {e}")
                    print(f"   Continuing with original WebM format...")
                
                # Step 1: Upload to Firebase Storage
                storage_url = None
                try:
                    from utils.utils import upload_base64_to_firebase_storage
                    storage_url = await upload_base64_to_firebase_storage(
                        base64_data=audio_data_to_upload,
                        file_name=upload_file_name,
                        file_type=upload_file_type
                    )
                    print(f"✅ Voice uploaded to Storage: {storage_url}")
                except Exception as e:
                    print(f"⚠️ Failed to upload to Storage: {e}")
                    if "404" in str(e) and "bucket does not exist" in str(e).lower():
                        print(f"   📌 HINT: Check storageBucket in data/firebase_data.json")
                        print(f"   📌 Actual bucket: linas-ai-bot.firebasestorage.app (not appspot.com)")
                    storage_url = None
                
                # Step 2: Save to Firebase Firestore
                print(f"📝 Saving voice metadata to Firebase Firestore...")
                await save_conversation_message_to_firestore(
                    user_id=user_id,
                    role="operator",
                    text="[Voice Message from Operator]",
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={
                        "operator_id": operator_id,
                        "handled_by": "human",
                        "type": "voice",
                        "audio_url": storage_url,  # Store the public URL with key name 'audio_url' for easy retrieval
                        "audio_mime_type": upload_file_type,
                        "message_length": len(message)
                    }
                )
                
                # Step 3: Send voice message via WhatsApp
                print(f"🎙️ Sending voice message via WhatsApp to {user_id}...")
                try:
                    if storage_url:
                        whatsapp_audio_url = build_whatsapp_audio_delivery_url(storage_url)
                        print(f"📤 Proxy URL for WhatsApp: {whatsapp_audio_url}")
                        send_result = await adapter.send_audio_message(user_id, whatsapp_audio_url)
                        if send_result.get("success"):
                            print(f"✅ Sent voice message via WhatsApp")
                        else:
                            error_msg = send_result.get("error", "Unknown error")
                            print(f"⚠️ WhatsApp audio send failed: {error_msg}")
                            print(f"⚠️ Audio URL was: {storage_url}")
                            return {
                                "success": False,
                                "error": f"WhatsApp audio send failed: {error_msg}",
                                "storage_url": storage_url,
                                "whatsapp_audio_url": whatsapp_audio_url
                            }
                    else:
                        # Fallback: send text notification if storage upload failed
                        text_notification = "تم استلام رسالة صوتية من المشغل. يرجى فتح لوحة المعلومات لسماعها."
                        await adapter.send_text_message(user_id, text_notification)
                        print(f"✅ Sent text notification (storage upload failed)")
                except Exception as e:
                    print(f"⚠️ Failed to send via WhatsApp: {e}")
                    import traceback
                    traceback.print_exc()
                    return {"success": False, "error": f"Failed to send voice: {str(e)}"}

                print(f"✅ Voice message processed and sent for {user_id}")

                return {
                    "success": True,
                    "message": "Voice message sent successfully",
                    "storage_url": storage_url,
                    "whatsapp_audio_url": build_whatsapp_audio_delivery_url(storage_url) if storage_url else None
                }
                    
            elif message_type == "image":
                # message contains base64 image data
                print(f"🖼️ Operator {operator_id} uploaded image for {user_id}")
                print(f"📝 Uploading image to Firebase Storage...")
                
                # Step 1: Upload to Firebase Storage
                storage_url = None
                try:
                    from utils.utils import upload_base64_to_firebase_storage
                    storage_url = await upload_base64_to_firebase_storage(
                        base64_data=message,
                        file_name=f"image_{user_id}_{int(__import__('time').time())}.jpg",
                        file_type="image/jpeg"
                    )
                    print(f"✅ Image uploaded to Storage: {storage_url}")
                except Exception as e:
                    print(f"⚠️ Failed to upload to Storage: {e}")
                    storage_url = None
                
                # Step 2: Save to Firebase Firestore
                print(f"📝 Saving image metadata to Firebase Firestore...")
                await save_conversation_message_to_firestore(
                    user_id=user_id,
                    role="operator",
                    text="[Image Message from Operator]",
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={
                        "operator_id": operator_id,
                        "handled_by": "human",
                        "type": "image",
                        "image_data": message,  # Store full base64 as backup
                        "image_url": storage_url,  # Store the public URL with key name 'image_url' for easy retrieval
                        "message_length": len(message)
                    }
                )
                
                # Step 3: Send image via Qiscus
                print(f"🖼️ Sending image via Qiscus to {user_id}...")
                try:
                    if storage_url:
                        # Send as native image message (displays in gallery on phone, not just a link)
                        await adapter.send_image_message(user_id, storage_url, caption="صورة من المشغل")
                        print(f"✅ Sent image as native image message via Qiscus")
                    else:
                        # Fallback: send text notification if storage upload failed
                        text_notification = "تم استلام صورة من المشغل. يرجى فتح لوحة المعلومات لعرضها."
                        await adapter.send_text_message(user_id, text_notification)
                        print(f"✅ Sent text notification (storage upload failed)")
                except Exception as e:
                    print(f"⚠️ Failed to send via Qiscus: {e}")
                    import traceback
                    traceback.print_exc()
                
                print(f"✅ Image message processed and sent for {user_id}")
                
                return {"success": True, "message": "Image message sent successfully", "storage_url": storage_url}
                    
            else:  # Default to text
                # Always save to Firestore first (for live chat history)
                await save_conversation_message_to_firestore(
                    user_id=user_id,
                    role="operator",
                    text=message,
                    conversation_id=conversation_id,
                    phone_number=phone_number,  # NOW PASSING PHONE_NUMBER
                    metadata={"operator_id": operator_id, "handled_by": "human"}
                )
                print(f"✅ Saved operator message to Firestore")

                # Try to send via WhatsApp adapter
                try:
                    result = await adapter.send_text_message(user_id, message)

                    if result.get("success"):
                        print(f"✅ Operator {operator_id} sent message to {user_id} via WhatsApp")
                        return {"success": True, "message": "Message sent successfully"}
                    else:
                        print(f"⚠️ WhatsApp send failed but message saved: {result.get('error')}")
                        return {"success": True, "message": "Message saved (WhatsApp send failed)", "warning": result.get('error')}
                except Exception as send_error:
                    print(f"⚠️ WhatsApp adapter error but message saved: {send_error}")
                    return {"success": True, "message": "Message saved (WhatsApp unavailable)", "warning": str(send_error)}
            
        except Exception as e:
            print(f"❌ Error sending operator message: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def update_operator_status(self, operator_id: str, status: str) -> Dict[str, Any]:
        """Update operator availability"""
        try:
            valid_statuses = ["available", "busy", "away"]
            if status not in valid_statuses:
                return {"success": False, "error": f"Invalid status. Must be one of: {valid_statuses}"}
            
            self.operator_status[operator_id] = status
            print(f"✅ Operator {operator_id} status: {status}")
            
            return {"success": True, "operator_id": operator_id, "status": status}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_conversation_details(self, user_id: str, conversation_id: str, max_messages: int = 100) -> Dict[str, Any]:
        """Get detailed conversation history

        Args:
            user_id: The user's ID
            conversation_id: The conversation document ID
            max_messages: Maximum number of messages to return (default 100, prevents timeout on large conversations)
        """
        try:
            db = get_firestore_db()
            if not db:
                return {"success": False, "error": "Firestore not initialized"}

            app_id = "linas-ai-bot-backend"
            conv_ref = db.collection("artifacts").document(app_id).collection("users").document(
                user_id
            ).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(conversation_id)

            # ✅ Use asyncio.to_thread to prevent blocking the event loop
            conv_doc = await asyncio.to_thread(conv_ref.get)
            if not conv_doc.exists:
                return {"success": False, "error": "Conversation not found"}

            conv_data = conv_doc.to_dict()
            messages = self._dedupe_messages(conv_data.get("messages", []))

            # ✅ Limit messages to prevent timeout on large conversations
            total_messages = len(messages)
            if total_messages > max_messages:
                print(f"⚠️ Conversation {conversation_id} has {total_messages} messages, returning last {max_messages}")
                messages = messages[-max_messages:]  # Get last N messages

            formatted_messages = []

            for msg in messages:
                # Skip smart messages (automated reminders) - they shouldn't appear in live chat
                if msg.get("metadata", {}).get("source") == "smart_message":
                    continue

                msg_data = {
                    "timestamp": self._parse_timestamp(msg.get("timestamp")).isoformat(),
                    "is_user": msg.get("role") == "user",
                    "content": msg.get("text", ""),
                    "text": msg.get("text", ""),
                    "type": msg.get("type", "text"),
                    "handled_by": msg.get("metadata", {}).get("handled_by", "bot"),
                    "role": msg.get("role")
                }

                # Add audio_url if it exists (for voice messages) - check both top level and metadata
                audio_url = msg.get("audio_url") or msg.get("metadata", {}).get("audio_url")
                if audio_url:
                    msg_data["audio_url"] = audio_url

                # Add image_url if it exists (for image messages) - check both top level and metadata
                image_url = msg.get("image_url") or msg.get("metadata", {}).get("image_url")
                if image_url:
                    msg_data["image_url"] = image_url

                formatted_messages.append(msg_data)

            return {
                "success": True,
                "conversation_id": conversation_id,
                "messages": formatted_messages,
                "total_messages": total_messages,
                "returned_messages": len(formatted_messages),
                "sentiment": conv_data.get("sentiment", "neutral"),
                "status": conv_data.get("status", "active")
            }

        except Exception as e:
            print(f"❌ Error getting conversation details: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get real-time metrics"""
        try:
            active_conversations = await self.get_active_conversations()
            waiting_queue = await self.get_waiting_queue()
            
            total_active = len(active_conversations)
            bot_handling = len([c for c in active_conversations if c["status"] == "bot"])
            human_handling = len([c for c in active_conversations if c["status"] == "human"])
            waiting_human = len(waiting_queue)
            
            sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
            for conv in active_conversations:
                sentiment = conv.get("sentiment", "neutral")
                sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
            
            avg_wait_time = 0
            if waiting_queue:
                total_wait = sum(item["wait_time_seconds"] for item in waiting_queue)
                avg_wait_time = total_wait / len(waiting_queue)
            
            return {
                "success": True,
                "metrics": {
                    "total_active_conversations": total_active,
                    "bot_handling": bot_handling,
                    "human_handling": human_handling,
                    "waiting_for_human": waiting_human,
                    "sentiment_distribution": sentiment_counts,
                    "average_wait_time_seconds": int(avg_wait_time),
                    "active_operators": len([op for op, status in self.operator_status.items() if status == "available"]),
                    "time_window_hours": 6
                },
                "timestamp": datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Error getting metrics: {e}")
            return {"success": False, "error": str(e)}

    def _normalize_phone_digits(self, value: Any) -> str:
        """Return digits-only phone value (supports +, spaces, dashes, 00 prefix)."""
        if value is None:
            return ""
        digits = re.sub(r"\D", "", str(value))
        if digits.startswith("00"):
            digits = digits[2:]
        return digits

    def _build_phone_variants(self, value: Any) -> set:
        """
        Build comparable phone variants to support mixed country-code/local searches.
        Example: +96176466674 -> {96176466674, 76466674, 6466674}
        """
        digits = self._normalize_phone_digits(value)
        if not digits:
            return set()

        variants = {digits}

        if digits.startswith("0") and len(digits) > 1:
            variants.add(digits[1:])

        # Lebanon-aware variants
        if digits.startswith("961") and len(digits) > 3:
            local_number = digits[3:]
            variants.add(local_number)
            if local_number.startswith("0") and len(local_number) > 1:
                variants.add(local_number[1:])
        elif len(digits) == 8:
            variants.add(f"961{digits}")
            if digits.startswith("0") and len(digits) > 1:
                variants.add(f"961{digits[1:]}")

        # Generic "local-part" fallback for other country codes.
        if len(digits) > 8:
            variants.add(digits[-8:])
        if len(digits) > 7:
            variants.add(digits[-7:])

        return {variant for variant in variants if len(variant) >= 2}

    def _phone_matches_search(self, search_term: str, *candidate_values: Any) -> bool:
        """Return True when normalized phone variants partially overlap."""
        search_variants = self._build_phone_variants(search_term)
        if not search_variants:
            return False

        for candidate_value in candidate_values:
            candidate_variants = self._build_phone_variants(candidate_value)
            for search_variant in search_variants:
                for candidate_variant in candidate_variants:
                    if search_variant in candidate_variant or candidate_variant in search_variant:
                        return True
        return False

    def _filter_conversations(self, conversations: List[Dict[str, Any]], search_term: str) -> List[Dict[str, Any]]:
        """Filter conversations by client name and/or phone (partial, normalized)."""
        normalized_search = (search_term or "").strip()
        if not normalized_search:
            return conversations

        lowered_search = normalized_search.lower()
        has_phone_digits = bool(self._normalize_phone_digits(normalized_search))

        filtered = []
        for conversation in conversations:
            user_name = str(conversation.get("user_name", "")).lower()
            if lowered_search in user_name:
                filtered.append(conversation)
                continue

            phone_candidates = [
                conversation.get("user_phone"),
                conversation.get("phone_clean"),
            ]
            user_id = conversation.get("user_id")
            user_id_digits = self._normalize_phone_digits(user_id)
            resolved_phone_digits = self._normalize_phone_digits(conversation.get("user_phone"))

            # Only consider user_id as phone fallback when no better phone is available.
            if user_id_digits and (not resolved_phone_digits or resolved_phone_digits == user_id_digits):
                phone_candidates.append(user_id)

            if has_phone_digits and self._phone_matches_search(
                normalized_search,
                *phone_candidates,
            ):
                filtered.append(conversation)

        return filtered

    def _choose_preferred_phone(self, current_phone: Optional[str], candidate_phone: str) -> str:
        """Prefer a richer display phone (with +country code / longer digits)."""
        if not current_phone:
            return candidate_phone

        current_digits = self._normalize_phone_digits(current_phone)
        candidate_digits = self._normalize_phone_digits(candidate_phone)

        if candidate_phone.startswith("+") and not current_phone.startswith("+"):
            return candidate_phone
        if len(candidate_digits) > len(current_digits):
            return candidate_phone

        return current_phone

    def _load_phone_room_mapping(self) -> Dict[str, str]:
        """Load `data/phone_to_room_mapping.json` with short TTL cache."""
        now = datetime.datetime.now(datetime.timezone.utc)
        if (
            self._phone_mapping_cache_time is not None
            and (now - self._phone_mapping_cache_time).total_seconds() < self.PHONE_MAPPING_CACHE_TTL
        ):
            return self._room_to_phone_cache

        phone_to_room = {}
        room_to_phone = {}

        mapping_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "phone_to_room_mapping.json",
        )

        try:
            with open(mapping_path, "r", encoding="utf-8") as mapping_file:
                mapping_data = json.load(mapping_file)
            raw_mapping = mapping_data.get("phone_to_room_mapping", {})
            if isinstance(raw_mapping, dict):
                for raw_phone, raw_room_id in raw_mapping.items():
                    room_id = str(raw_room_id).strip()
                    phone_value = str(raw_phone).strip()
                    normalized_phone = self._normalize_phone_digits(phone_value)

                    if not room_id or not normalized_phone:
                        continue

                    phone_to_room[normalized_phone] = room_id
                    room_to_phone[room_id] = self._choose_preferred_phone(
                        room_to_phone.get(room_id),
                        phone_value
                    )
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"⚠️ Failed to load phone_to_room_mapping.json: {e}")

        self._phone_to_room_cache = phone_to_room
        self._room_to_phone_cache = room_to_phone
        self._phone_mapping_cache_time = now
        return self._room_to_phone_cache

    def _get_mapped_phone_for_room(self, user_id: str) -> Optional[str]:
        """Return mapped phone for a room_id/user_id when available."""
        room_to_phone = self._load_phone_room_mapping()
        return room_to_phone.get(str(user_id))

    def _resolve_user_phone(self, user_id: str, customer_info: Optional[Dict[str, Any]]) -> Tuple[str, str]:
        """
        Resolve best phone for dashboard/search:
        1) customer_info
        2) runtime memory (config.user_data_whatsapp)
        3) static phone_to_room_mapping.json
        """
        customer_info = customer_info or {}
        user_data = config.user_data_whatsapp.get(user_id, {})

        phone_full = str(customer_info.get("phone_full") or "").strip()
        phone_clean_raw = str(customer_info.get("phone_clean") or "").strip()
        memory_phone = str(user_data.get("phone_number") or "").strip()
        mapped_phone = str(self._get_mapped_phone_for_room(user_id) or "").strip()

        user_digits = self._normalize_phone_digits(user_id)
        phone_full_digits = self._normalize_phone_digits(phone_full)
        memory_digits = self._normalize_phone_digits(memory_phone)
        mapped_digits = self._normalize_phone_digits(mapped_phone)

        # If Firestore saved room_id instead of real phone, replace it.
        if phone_full_digits and user_digits and phone_full_digits == user_digits:
            if mapped_digits and mapped_digits != user_digits:
                phone_full = mapped_phone
                phone_full_digits = mapped_digits
            elif memory_digits and memory_digits != user_digits:
                phone_full = memory_phone
                phone_full_digits = memory_digits

        # If still missing, fallback to memory then static mapping.
        if not phone_full_digits:
            if memory_digits:
                phone_full = memory_phone
                phone_full_digits = memory_digits
            elif mapped_digits:
                phone_full = mapped_phone
                phone_full_digits = mapped_digits

        clean_digits = self._normalize_phone_digits(phone_clean_raw)
        if clean_digits and user_digits and clean_digits == user_digits and phone_full_digits:
            clean_digits = phone_full_digits
        if not clean_digits:
            clean_digits = phone_full_digits

        # Backward-compatible "clean" format used elsewhere in the app.
        if clean_digits.startswith("961") and len(clean_digits) > 8:
            phone_clean = clean_digits[3:]
        else:
            phone_clean = clean_digits

        if not phone_full:
            phone_full = "Unknown"
        if not phone_clean:
            phone_clean = "Unknown"

        return phone_full, phone_clean
    
    def _parse_timestamp(self, timestamp) -> datetime.datetime:
        """Parse various timestamp formats - always returns UTC-aware datetime"""
        if isinstance(timestamp, str):
            try:
                # Handle ISO format strings
                dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                # If naive (no timezone), assume it's UTC
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                return dt
            except:
                return datetime.datetime.now(datetime.timezone.utc)
        elif hasattr(timestamp, 'timestamp'):
            # Firestore timestamp object - .timestamp() returns UTC epoch seconds
            return datetime.datetime.fromtimestamp(timestamp.timestamp(), tz=datetime.timezone.utc)
        elif hasattr(timestamp, 'seconds'):
            # Firestore timestamp with seconds attribute - epoch seconds are always UTC
            return datetime.datetime.fromtimestamp(timestamp.seconds, tz=datetime.timezone.utc)
        else:
            return datetime.datetime.now(datetime.timezone.utc)


# Global instance
live_chat_service = LiveChatService()
