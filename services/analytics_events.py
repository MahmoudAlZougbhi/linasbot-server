# -*- coding: utf-8 -*-
"""
Analytics Events System
Simple append-only event logging for analytics
Each event is one line in a JSONL file
"""

import json
import os
import datetime
import math
from typing import Dict, Any, List, Optional
from collections import defaultdict


class AnalyticsEvents:
    """Handles analytics event logging and aggregation"""
    
    def __init__(self):
        self.events_file = "data/analytics_events.jsonl"
        # Session rule used for Conversation 1/2/3 counting
        self.conversation_session_gap_minutes = 30
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Create events file if it doesn't exist"""
        if not os.path.exists(self.events_file):
            os.makedirs(os.path.dirname(self.events_file), exist_ok=True)
            open(self.events_file, 'a').close()
    
    def _append_event(self, event: Dict[str, Any]):
        """Append a single event to the file"""
        try:
            event["timestamp"] = datetime.datetime.now().isoformat()
            with open(self.events_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"❌ Error appending event: {e}")

    @staticmethod
    def _normalize_user_id(user_id: Any) -> Optional[str]:
        """Normalize user IDs for stable deduplication."""
        if user_id is None:
            return None
        normalized = str(user_id).strip()
        if not normalized:
            return None
        normalized = normalized.replace(" ", "").replace("-", "")
        if normalized.startswith("+"):
            normalized = normalized[1:]
        return normalized

    @staticmethod
    def _parse_timestamp(timestamp: Any) -> Optional[datetime.datetime]:
        """
        Parse supported timestamp formats into naive local datetime.
        Supports ISO values with either "T" or space separators.
        """
        if not timestamp:
            return None
        try:
            if isinstance(timestamp, datetime.datetime):
                dt = timestamp
            else:
                ts = str(timestamp).strip().replace("Z", "+00:00")
                dt = datetime.datetime.fromisoformat(ts)
            if dt.tzinfo is not None:
                return dt.astimezone().replace(tzinfo=None)
            return dt
        except Exception:
            return None
    
    # ==================== EVENT LOGGING METHODS ====================
    
    def log_message(self, source: str, msg_type: str, user_id: str, language: str = "ar", 
                   sentiment: str = "neutral", tokens: int = 0, cost_usd: float = 0.0, 
                   model: str = None, response_time_ms: float = None, message_length: int = 0):
        """
        Log a message event
        
        Args:
            source: "user" | "bot" | "human"
            msg_type: "text" | "voice" | "image"
            user_id: User identifier
            language: "ar" | "en" | "fr" | "franco"
            sentiment: "positive" | "neutral" | "negative"
            tokens: Number of tokens used (for bot messages)
            cost_usd: Cost in USD (for bot messages)
            model: AI model used (e.g., "gpt-4o", "whisper-1")
            response_time_ms: Response time in milliseconds (for bot messages)
            message_length: Length of message in characters
        """
        self._append_event({
            "type": "message",
            "source": source,
            "msg_type": msg_type,
            "user_id": user_id,
            "language": language,
            "sentiment": sentiment,
            "tokens": tokens,
            "cost_usd": cost_usd,
            "model": model,
            "response_time_ms": response_time_ms,
            "message_length": message_length
        })
    
    def log_conversation_start(self, user_id: str, conversation_id: str, is_new_user: bool = False):
        """Log when a new conversation starts"""
        self._append_event({
            "type": "conversation_start",
            "user_id": user_id,
            "conversation_id": conversation_id,
            "is_new_user": is_new_user
        })
    
    def log_gender(self, user_id: str, gender: str):
        """
        Log user gender
        
        Args:
            gender: "male" | "female" | "unknown"
        """
        self._append_event({
            "type": "gender",
            "user_id": user_id,
            "gender": gender
        })
    
    def log_service_request(self, user_id: str, service: str):
        """Log when user asks about a service"""
        self._append_event({
            "type": "service_request",
            "user_id": user_id,
            "service": service
        })
    
    def log_appointment(self, user_id: str, service: str, status: str, messages_count: int = 0):
        """
        Log appointment event
        
        Args:
            status: "requested" | "booked" | "confirmed" | "rescheduled" | "cancelled"
            messages_count: Number of messages in conversation (for conversion tracking)
        """
        self._append_event({
            "type": "appointment",
            "user_id": user_id,
            "service": service,
            "status": status,
            "messages_count": messages_count
        })
    
    def log_feedback(self, user_id: str, feedback_type: str, reason: str = None):
        """
        Log user feedback
        
        Args:
            feedback_type: "good" | "wrong" | "inappropriate" | "unclear"
            reason: Optional reason for negative feedback
        """
        self._append_event({
            "type": "feedback",
            "user_id": user_id,
            "feedback_type": feedback_type,
            "reason": reason
        })
    
    def log_escalation(self, user_id: str, escalation_type: str, reason: str = None):
        """
        Log escalation event
        
        Args:
            escalation_type: "human_handover" | "complaint" | "technical_issue" | "bot_failure"
            reason: Optional reason for escalation
        """
        self._append_event({
            "type": "escalation",
            "user_id": user_id,
            "escalation_type": escalation_type,
            "reason": reason
        })
    
    def log_topic(self, user_id: str, topic: str, category: str = "general"):
        """Log trending topic/question"""
        self._append_event({
            "type": "topic",
            "user_id": user_id,
            "topic": topic,
            "category": category
        })
    
    def _safe_int(self, value: Any) -> int:
        """Parse integer safely from event payloads."""
        try:
            if value is None:
                return 0
            return int(value)
        except (TypeError, ValueError):
            return 0
    
    def _safe_float(self, value: Any) -> float:
        """Parse float safely from event payloads."""
        try:
            if value is None:
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    
    def _mask_user_id(self, user_id: Any) -> str:
        """Mask user id before returning examples to dashboard."""
        user = str(user_id or "")
        if len(user) <= 4:
            return user
        return f"...{user[-4:]}"
    
    def _build_conversation_type_metrics(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build Conversation 1/2/3 metrics from event logs.

        Counting model:
        - Events are grouped by user_id.
        - A new conversation session starts after N minutes of inactivity.
        - Each session is labeled by the highest stage reached:
          Conversation 1 -> message-only/general session
          Conversation 2 -> qualified session (gender or service intent captured)
          Conversation 3 -> appointment action detected
        """
        try:
            events_by_user = defaultdict(list)
            for event in events:
                user_id = event.get("user_id")
                timestamp = event.get("timestamp")
                if not user_id or not timestamp:
                    continue
                try:
                    dt = datetime.datetime.fromisoformat(timestamp)
                except Exception:
                    continue
                events_by_user[str(user_id)].append((dt, event))
            
            session_gap_seconds = self.conversation_session_gap_minutes * 60
            sessions = []
            
            for user_id, user_events in events_by_user.items():
                user_events.sort(key=lambda item: item[0])
                current_session = []
                
                for dt, event in user_events:
                    if not current_session:
                        current_session = [(dt, event)]
                        continue
                    
                    previous_dt = current_session[-1][0]
                    inactivity = (dt - previous_dt).total_seconds()
                    
                    if inactivity > session_gap_seconds:
                        sessions.append({
                            "user_id": user_id,
                            "start": current_session[0][0],
                            "end": current_session[-1][0],
                            "events": [entry[1] for entry in current_session],
                        })
                        current_session = [(dt, event)]
                    else:
                        current_session.append((dt, event))
                
                if current_session:
                    sessions.append({
                        "user_id": user_id,
                        "start": current_session[0][0],
                        "end": current_session[-1][0],
                        "events": [entry[1] for entry in current_session],
                    })
            
            definitions = {
                "conversation_1": "General conversation session with no qualification signal and no appointment event.",
                "conversation_2": "Qualified conversation session where intent/profile is captured (service_request or gender), but no appointment event yet.",
                "conversation_3": "Conversion conversation session that includes an appointment event (requested/booked/confirmed/rescheduled/cancelled).",
            }
            
            stages = {
                "conversation_1": {
                    "id": "conversation_1",
                    "label": "Conversation 1",
                    "description": definitions["conversation_1"],
                    "exclusive_count": 0,
                    "funnel_count": 0,
                    "total_events": 0,
                    "message_events": 0,
                    "user_messages": 0,
                    "bot_messages": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "examples": [],
                },
                "conversation_2": {
                    "id": "conversation_2",
                    "label": "Conversation 2",
                    "description": definitions["conversation_2"],
                    "exclusive_count": 0,
                    "funnel_count": 0,
                    "total_events": 0,
                    "message_events": 0,
                    "user_messages": 0,
                    "bot_messages": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "examples": [],
                },
                "conversation_3": {
                    "id": "conversation_3",
                    "label": "Conversation 3",
                    "description": definitions["conversation_3"],
                    "exclusive_count": 0,
                    "funnel_count": 0,
                    "total_events": 0,
                    "message_events": 0,
                    "user_messages": 0,
                    "bot_messages": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "examples": [],
                },
            }
            
            stage_rank = {
                "conversation_1": 1,
                "conversation_2": 2,
                "conversation_3": 3,
            }
            
            for session in sessions:
                session_events = session["events"]
                
                has_gender = False
                has_service_request = False
                has_appointment = False
                appointment_statuses = []
                
                session_total_events = len(session_events)
                session_message_events = 0
                session_user_messages = 0
                session_bot_messages = 0
                session_tokens = 0
                session_cost = 0.0
                sequence_parts = []
                unique_event_types = set()
                
                for event in session_events:
                    event_type = event.get("type", "unknown")
                    unique_event_types.add(event_type)
                    
                    if event_type == "gender":
                        has_gender = True
                        sequence_parts.append("gender")
                    elif event_type == "service_request":
                        has_service_request = True
                        sequence_parts.append("service_request")
                    elif event_type == "appointment":
                        has_appointment = True
                        status = str(event.get("status", "unknown"))
                        appointment_statuses.append(status)
                        sequence_parts.append(f"appointment({status})")
                    elif event_type == "message":
                        source = str(event.get("source", "unknown"))
                        session_message_events += 1
                        sequence_parts.append(f"message({source})")
                        
                        if source == "user":
                            session_user_messages += 1
                        elif source == "bot":
                            session_bot_messages += 1
                            session_tokens += max(self._safe_int(event.get("tokens")), 0)
                            session_cost += max(self._safe_float(event.get("cost_usd")), 0.0)
                    else:
                        sequence_parts.append(event_type)
                
                if has_appointment:
                    stage_key = "conversation_3"
                elif has_service_request or has_gender:
                    stage_key = "conversation_2"
                else:
                    stage_key = "conversation_1"
                
                stage = stages[stage_key]
                stage["exclusive_count"] += 1
                stage["total_events"] += session_total_events
                stage["message_events"] += session_message_events
                stage["user_messages"] += session_user_messages
                stage["bot_messages"] += session_bot_messages
                stage["total_tokens"] += session_tokens
                stage["estimated_cost_usd"] += session_cost
                
                session_stage_rank = stage_rank[stage_key]
                for funnel_key, required_rank in stage_rank.items():
                    if session_stage_rank >= required_rank:
                        stages[funnel_key]["funnel_count"] += 1
                
                if len(stage["examples"]) < 3:
                    preview_sequence = " -> ".join(sequence_parts[:8])
                    if len(sequence_parts) > 8:
                        preview_sequence += " -> ..."
                    
                    stage["examples"].append({
                        "user_id_masked": self._mask_user_id(session["user_id"]),
                        "session_start": session["start"].isoformat(),
                        "session_end": session["end"].isoformat(),
                        "event_types": sorted(unique_event_types),
                        "event_sequence": preview_sequence,
                        "appointment_statuses": sorted(set(appointment_statuses)),
                        "bot_tokens": session_tokens,
                        "estimated_cost_usd": round(session_cost, 6),
                    })
            
            total_sessions = len(sessions)
            estimated_total_cost = sum(stage["estimated_cost_usd"] for stage in stages.values())
            
            ordered_keys = ["conversation_1", "conversation_2", "conversation_3"]
            stage_list = []
            for key in ordered_keys:
                stage = stages[key]
                count = stage["exclusive_count"]
                stage["share_of_sessions_pct"] = round((count / total_sessions) * 100, 1) if total_sessions > 0 else 0
                stage["avg_tokens_per_conversation"] = round(stage["total_tokens"] / count, 1) if count > 0 else 0
                stage["avg_estimated_cost_usd"] = round(stage["estimated_cost_usd"] / count, 6) if count > 0 else 0
                stage["estimated_cost_usd"] = round(stage["estimated_cost_usd"], 6)
                stage["estimated_cost_share_pct"] = round(
                    (stage["estimated_cost_usd"] / estimated_total_cost) * 100, 1
                ) if estimated_total_cost > 0 else 0
                stage["allocated_real_cost_usd"] = None
                stage_list.append(stage)
            
            return {
                "counting": {
                    "method": (
                        "Sessionized by user_id and inactivity gap. "
                        "Each session is counted once using the highest stage reached."
                    ),
                    "session_gap_minutes": self.conversation_session_gap_minutes,
                },
                "definitions": definitions,
                "total_sessions": total_sessions,
                "exclusive_counts": {
                    "conversation_1": stages["conversation_1"]["exclusive_count"],
                    "conversation_2": stages["conversation_2"]["exclusive_count"],
                    "conversation_3": stages["conversation_3"]["exclusive_count"],
                },
                "funnel_counts": {
                    "conversation_1": stages["conversation_1"]["funnel_count"],
                    "conversation_2": stages["conversation_2"]["funnel_count"],
                    "conversation_3": stages["conversation_3"]["funnel_count"],
                },
                "stages": stage_list,
                "billing": {
                    "source": "estimated_event_costs",
                    "estimated_total_cost_usd": round(estimated_total_cost, 6),
                    "openai_total_cost_usd": None,
                    "note": (
                        "Estimated costs are summed from message events (source=bot, cost_usd). "
                        "If OpenAI real billing is enabled in the API response, real total cost is "
                        "allocated across Conversation 1/2/3 by estimated cost share."
                    ),
                },
            }
            
        except Exception as e:
            print(f"❌ Error building conversation type metrics: {e}")
            return {
                "counting": {
                    "method": "Sessionized by user_id and inactivity gap",
                    "session_gap_minutes": self.conversation_session_gap_minutes,
                },
                "definitions": {},
                "total_sessions": 0,
                "exclusive_counts": {
                    "conversation_1": 0,
                    "conversation_2": 0,
                    "conversation_3": 0,
                },
                "funnel_counts": {
                    "conversation_1": 0,
                    "conversation_2": 0,
                    "conversation_3": 0,
                },
                "stages": [],
                "billing": {
                    "source": "estimated_event_costs",
                    "estimated_total_cost_usd": 0.0,
                    "openai_total_cost_usd": None,
                    "note": "Unable to compute conversation stage billing from events.",
                },
            }
    
    # ==================== AGGREGATION METHODS ====================
    
    def get_events(self, days: Optional[int] = 7, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Read events from file and filter by date range
        
        Args:
            days: Number of days to include
            event_type: Optional filter by event type
            
        Returns:
            List of events
        """
        try:
            events = []
            cutoff_date = None
            if days is not None:
                cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
            
            if not os.path.exists(self.events_file):
                return []
            
            with open(self.events_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        event_date = self._parse_timestamp(event.get("timestamp"))
                        if not event_date:
                            continue
                        normalized_user_id = self._normalize_user_id(event.get("user_id"))
                        if normalized_user_id:
                            event["user_id"] = normalized_user_id
                        
                        # Filter by date
                        if cutoff_date is None or event_date >= cutoff_date:
                            # Filter by type if specified
                            if event_type is None or event.get("type") == event_type:
                                events.append(event)
                    except:
                        continue
            
            return events
            
        except Exception as e:
            print(f"❌ Error reading events: {e}")
            return []
    
    def aggregate_analytics(self, days: int = 7) -> Dict[str, Any]:
        """
        Aggregate all events into analytics data
        
        Args:
            days: Number of days to include
            
        Returns:
            Dictionary with all analytics metrics
        """
        try:
            days = max(self._safe_int(days), 1)
            now = datetime.datetime.now()
            range_start = now - datetime.timedelta(days=days)
            today_date = now.date()
            events = self.get_events(days=days)
            all_events = self.get_events(days=None)

            # Build first-seen index from the full event history.
            first_seen_by_user: Dict[str, datetime.datetime] = {}
            for event in all_events:
                user_id = self._normalize_user_id(event.get("user_id"))
                event_dt = self._parse_timestamp(event.get("timestamp"))
                if not user_id or not event_dt:
                    continue
                existing_first_seen = first_seen_by_user.get(user_id)
                if existing_first_seen is None or event_dt < existing_first_seen:
                    first_seen_by_user[user_id] = event_dt
            
            # Initialize counters
            stats = {
                "overview": {
                    "total_messages": 0,
                    "total_conversations": 0,
                    "unique_users": set(),
                    "new_users": 0,
                    "active_user_message_users": set()
                },
                "messages": {
                    "by_type": defaultdict(int),
                    "by_source": defaultdict(int),
                    "by_language": defaultdict(int),
                    "daily": defaultdict(lambda: defaultdict(int)),
                    "hourly": defaultdict(int)
                },
                "sentiment": defaultdict(int),
                "genders": defaultdict(int),
                "services": defaultdict(int),
                "appointments": {
                    "requested": 0,
                    "booked": 0,
                    "confirmed": 0,
                    "rescheduled": 0,
                    "cancelled": 0,
                    "by_service": defaultdict(lambda: defaultdict(int))
                },
                "feedback": {
                    "total": 0,
                    "likes": 0,
                    "dislikes": 0,
                    "reasons": defaultdict(int)
                },
                "escalations": {
                    "total": 0,
                    "by_type": defaultdict(int)
                },
                "ai_performance": {
                    "total_response_time": 0,
                    "response_count": 0,
                    "min_response_time": None,
                    "max_response_time": None,
                    "response_times": [],
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "by_model": defaultdict(lambda: {"tokens": 0, "cost": 0.0})
                },
                "conversions": {
                    "inquiries": 0,
                    "qualified_leads": 0,
                    "appointment_requests": 0,
                    "bookings": 0,
                    "messages_to_booking": [],
                    "inquiry_users": set()
                },
                "new_client_metrics": {
                    "all_new_users": set(),
                    "asked_users": set(),
                    "booked_users": set(),
                    "services_by_user": defaultdict(set),
                    "booked_services_by_user": defaultdict(set)
                },
                "services_today": {
                    "date": today_date.isoformat(),
                    "mentions_by_service": defaultdict(int),
                    "users_by_service": defaultdict(set),
                    "all_users": set()
                },
            }
            
            # Process each event
            for event in events:
                event_type = event.get("type")
                user_id = self._normalize_user_id(event.get("user_id"))
                if user_id:
                    event["user_id"] = user_id
                dt = self._parse_timestamp(event.get("timestamp"))
                
                # Track unique users
                if user_id:
                    stats["overview"]["unique_users"].add(user_id)
                    first_seen = first_seen_by_user.get(user_id)
                    if first_seen and range_start <= first_seen <= now:
                        stats["new_client_metrics"]["all_new_users"].add(user_id)
                
                # Parse timestamp for time-based stats
                if dt:
                    date_key = dt.strftime("%Y-%m-%d")
                    hour_key = f"{dt.hour:02d}:00"
                else:
                    date_key = None
                    hour_key = None
                
                # Process by event type
                if event_type == "message":
                    stats["overview"]["total_messages"] += 1
                    stats["messages"]["by_type"][event.get("msg_type", "text")] += 1
                    stats["messages"]["by_source"][event.get("source", "user")] += 1
                    stats["messages"]["by_language"][event.get("language", "ar")] += 1
                    
                    sentiment = event.get("sentiment")
                    if sentiment:
                        stats["sentiment"][sentiment] += 1
                    
                    # Time-based
                    if date_key:
                        stats["messages"]["daily"][date_key]["total"] += 1
                        stats["messages"]["daily"][date_key][event.get("msg_type", "text")] += 1
                        stats["messages"]["daily"][date_key][event.get("language", "ar")] += 1
                    if hour_key:
                        stats["messages"]["hourly"][hour_key] += 1
                    
                    # AI performance (bot messages only)
                    if event.get("source") == "bot":
                        response_time = self._safe_float(event.get("response_time_ms"))
                        if response_time > 0:
                            stats["ai_performance"]["total_response_time"] += response_time
                            stats["ai_performance"]["response_count"] += 1
                            stats["ai_performance"]["response_times"].append(response_time)
                            
                            if stats["ai_performance"]["min_response_time"] is None:
                                stats["ai_performance"]["min_response_time"] = response_time
                            else:
                                stats["ai_performance"]["min_response_time"] = min(
                                    stats["ai_performance"]["min_response_time"], response_time
                                )
                            
                            if stats["ai_performance"]["max_response_time"] is None:
                                stats["ai_performance"]["max_response_time"] = response_time
                            else:
                                stats["ai_performance"]["max_response_time"] = max(
                                    stats["ai_performance"]["max_response_time"], response_time
                                )
                        
                        tokens = max(self._safe_int(event.get("tokens")), 0)
                        cost = max(self._safe_float(event.get("cost_usd")), 0.0)
                        model = event.get("model", "unknown")
                        
                        if tokens > 0:
                            stats["ai_performance"]["total_tokens"] += tokens
                            stats["ai_performance"]["by_model"][model]["tokens"] += tokens
                        
                        if cost > 0:
                            stats["ai_performance"]["total_cost"] += cost
                            stats["ai_performance"]["by_model"][model]["cost"] += cost
                    elif event.get("source") == "user" and user_id:
                        stats["overview"]["active_user_message_users"].add(user_id)
                        stats["conversions"]["inquiry_users"].add(user_id)
                
                elif event_type == "conversation_start":
                    stats["overview"]["total_conversations"] += 1
                    if event.get("is_new_user"):
                        stats["overview"]["new_users"] += 1
                
                elif event_type == "gender":
                    gender = event.get("gender")
                    if gender:
                        stats["genders"][gender] += 1
                
                elif event_type == "service_request":
                    service = event.get("service")
                    if user_id:
                        stats["conversions"]["inquiry_users"].add(user_id)
                    if service:
                        stats["services"][service] += 1
                        stats["conversions"]["qualified_leads"] += 1
                        if dt and dt.date() == today_date:
                            stats["services_today"]["mentions_by_service"][service] += 1
                            if user_id:
                                stats["services_today"]["users_by_service"][service].add(user_id)
                                stats["services_today"]["all_users"].add(user_id)
                    if user_id and user_id in stats["new_client_metrics"]["all_new_users"]:
                        stats["new_client_metrics"]["asked_users"].add(user_id)
                        if service:
                            stats["new_client_metrics"]["services_by_user"][user_id].add(service)
                
                elif event_type == "appointment":
                    status = event.get("status")
                    service = event.get("service")
                    
                    if status == "requested":
                        stats["appointments"]["requested"] += 1
                        stats["conversions"]["appointment_requests"] += 1
                    elif status == "booked":
                        stats["appointments"]["booked"] += 1
                        stats["conversions"]["bookings"] += 1
                        
                        messages_count = max(self._safe_int(event.get("messages_count")), 0)
                        if messages_count > 0:
                            stats["conversions"]["messages_to_booking"].append(messages_count)
                        if user_id and user_id in stats["new_client_metrics"]["all_new_users"]:
                            stats["new_client_metrics"]["booked_users"].add(user_id)
                            if service:
                                stats["new_client_metrics"]["booked_services_by_user"][user_id].add(service)
                    elif status == "confirmed":
                        stats["appointments"]["confirmed"] += 1
                    elif status == "rescheduled":
                        stats["appointments"]["rescheduled"] += 1
                    elif status == "cancelled":
                        stats["appointments"]["cancelled"] += 1
                    
                    if service and status:
                        stats["appointments"]["by_service"][service][status] += 1
                
                elif event_type == "feedback":
                    stats["feedback"]["total"] += 1
                    feedback_type = event.get("feedback_type")
                    
                    if feedback_type == "good":
                        stats["feedback"]["likes"] += 1
                    else:
                        stats["feedback"]["dislikes"] += 1
                        reason = event.get("reason", feedback_type)
                        if reason:
                            stats["feedback"]["reasons"][reason] += 1
                
                elif event_type == "escalation":
                    stats["escalations"]["total"] += 1
                    escalation_type = event.get("escalation_type")
                    if escalation_type:
                        stats["escalations"]["by_type"][escalation_type] += 1
            
            # Normalize counters and fallback values.
            stats["conversions"]["inquiries"] = len(stats["conversions"]["inquiry_users"])
            if stats["overview"]["total_conversations"] == 0:
                stats["overview"]["total_conversations"] = len(stats["overview"]["active_user_message_users"])
            if stats["overview"]["new_users"] == 0:
                stats["overview"]["new_users"] = len(stats["new_client_metrics"]["all_new_users"])

            # Convert sets to counts
            stats["overview"]["unique_users"] = len(stats["overview"]["unique_users"])
            
            # Build final response
            response = self._format_analytics_response(stats, days)
            if response.get("success"):
                response["conversation_types"] = self._build_conversation_type_metrics(events)
            return response
            
        except Exception as e:
            print(f"❌ Error aggregating analytics: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def _format_analytics_response(self, stats: Dict, days: int) -> Dict[str, Any]:
        """Format aggregated stats into API response"""
        
        # Calculate rates and percentages
        total_messages = stats["overview"]["total_messages"]
        total_conversations = stats["overview"]["total_conversations"]
        total_booked = stats["appointments"]["booked"]
        total_feedback = stats["feedback"]["total"]
        inquiries = stats["conversions"]["inquiries"]
        total_users = stats["overview"]["unique_users"]
        new_users = stats["overview"]["new_users"]

        avg_messages_per_day = round((total_messages / days), 1) if days > 0 else 0
        avg_messages_per_conversation = round((total_messages / total_conversations), 1) if total_conversations > 0 else 0
        
        # Build daily summaries
        daily_summaries = []
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=days)
        current_date = start_date.date()
        
        while current_date <= end_date.date():
            date_key = current_date.strftime("%Y-%m-%d")
            day_data = stats["messages"]["daily"].get(date_key, {})
            
            daily_summaries.append({
                "date": date_key,
                "total_messages": day_data.get("total", 0),
                "text_messages": day_data.get("text", 0),
                "voice_messages": day_data.get("voice", 0),
                "image_messages": day_data.get("image", 0),
                "language_ar": day_data.get("ar", 0),
                "language_en": day_data.get("en", 0),
                "language_fr": day_data.get("fr", 0),
                "language_franco": day_data.get("franco", 0)
            })
            
            current_date += datetime.timedelta(days=1)
        
        # Calculate percentages
        def calc_percentages(counts_dict):
            total = sum(counts_dict.values())
            if total == 0:
                return {}
            return {k: round((v / total) * 100, 1) for k, v in counts_dict.items()}
        
        # Build service list
        service_list = []
        total_service_requests = sum(stats["services"].values())
        for service, count in sorted(stats["services"].items(), key=lambda x: x[1], reverse=True):
            percentage = round((count / total_service_requests) * 100, 1) if total_service_requests > 0 else 0
            service_list.append({
                "name": service,
                "count": count,
                "percentage": percentage
            })
        
        # Calculate averages
        avg_response_time = 0
        if stats["ai_performance"]["response_count"] > 0:
            avg_response_time = stats["ai_performance"]["total_response_time"] / stats["ai_performance"]["response_count"]
        
        avg_messages_to_booking = 0
        if stats["conversions"]["messages_to_booking"]:
            avg_messages_to_booking = sum(stats["conversions"]["messages_to_booking"]) / len(stats["conversions"]["messages_to_booking"])

        # Calculate p95 response time
        response_times = sorted(stats["ai_performance"]["response_times"])
        p95_response_time = 0
        if response_times:
            p95_index = max(0, math.ceil(len(response_times) * 0.95) - 1)
            p95_response_time = response_times[p95_index]

        # New client metrics
        new_client_metrics = stats["new_client_metrics"]
        new_client_users = set(new_client_metrics["all_new_users"])
        new_client_booked_users = set(new_client_metrics["booked_users"])
        new_client_asked_users = set(new_client_metrics["asked_users"])
        new_client_asked_not_booked_users = sorted(new_client_asked_users - new_client_booked_users)
        new_client_booked_users_sorted = sorted(new_client_booked_users)
        new_client_not_booked_users = sorted(new_client_users - new_client_booked_users)

        booked_details = []
        for user_id in new_client_booked_users_sorted:
            discussed = set(new_client_metrics["services_by_user"].get(user_id, set()))
            booked = set(new_client_metrics["booked_services_by_user"].get(user_id, set()))
            booked_details.append({
                "user_id": user_id,
                "services": sorted(discussed | booked)
            })

        not_booked_details = []
        for user_id in new_client_not_booked_users:
            discussed = sorted(new_client_metrics["services_by_user"].get(user_id, set()))
            not_booked_details.append({
                "user_id": user_id,
                "services": discussed
            })

        asked_not_booked_details = []
        for user_id in new_client_asked_not_booked_users:
            discussed = sorted(new_client_metrics["services_by_user"].get(user_id, set()))
            asked_not_booked_details.append({
                "user_id": user_id,
                "services": discussed
            })

        # Services discussed today
        services_today_metrics = stats["services_today"]
        services_discussed_today = []
        for service, mentions in sorted(
            services_today_metrics["mentions_by_service"].items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            services_discussed_today.append({
                "service": service,
                "mentions": mentions,
                "unique_clients": len(services_today_metrics["users_by_service"].get(service, set()))
            })
        
        return {
            "success": True,
            "overview": {
                "total_messages": total_messages,
                "total_conversations": total_conversations,
                "total_users": total_users,
                "new_users": new_users,
                "returning_users": max(total_users - new_users, 0),
                "avg_messages_per_day": avg_messages_per_day,
                "avg_messages_per_conversation": avg_messages_per_conversation
            },
            "daily_summaries": daily_summaries,
            "hourly_distribution": dict(stats["messages"]["hourly"]),
            "demographics": {
                "languages": {
                    "counts": dict(stats["messages"]["by_language"]),
                    "percentages": calc_percentages(stats["messages"]["by_language"])
                },
                "genders": {
                    "counts": dict(stats["genders"]),
                    "percentages": calc_percentages(stats["genders"])
                }
            },
            "sentiment_distribution": dict(stats["sentiment"]),
            "services": {
                "most_requested": service_list[:10],
                "discussed_today": services_discussed_today
            },
            "appointments": {
                "total_booked": total_booked,
                "requested": stats["appointments"]["requested"],
                "confirmed": stats["appointments"]["confirmed"],
                "rescheduled": stats["appointments"]["rescheduled"],
                "cancelled": stats["appointments"]["cancelled"],
                "confirmation_rate": round((stats["appointments"]["confirmed"] / total_booked) * 100, 1) if total_booked > 0 else 0,
                "reschedule_rate": round((stats["appointments"]["rescheduled"] / total_booked) * 100, 1) if total_booked > 0 else 0,
                "cancellation_rate": round((stats["appointments"]["cancelled"] / total_booked) * 100, 1) if total_booked > 0 else 0
            },
            "satisfaction": {
                "total_feedback": total_feedback,
                "likes": stats["feedback"]["likes"],
                "dislikes": stats["feedback"]["dislikes"],
                "satisfaction_rate": round((stats["feedback"]["likes"] / total_feedback) * 100, 1) if total_feedback > 0 else 0,
                "dislike_reasons": dict(stats["feedback"]["reasons"])
            },
            "escalations": {
                "total_escalations": stats["escalations"]["total"],
                "human_handover": stats["escalations"]["by_type"].get("human_handover", 0),
                "complaints": stats["escalations"]["by_type"].get("complaint", 0),
                "technical_issues": stats["escalations"]["by_type"].get("technical_issue", 0)
            },
            "performance": {
                "avg_response_time_ms": round(avg_response_time, 0),
                "min_response_time_ms": stats["ai_performance"]["min_response_time"] or 0,
                "max_response_time_ms": stats["ai_performance"]["max_response_time"] or 0,
                "p95_response_time_ms": round(p95_response_time, 0) if p95_response_time else 0,
                "total_requests": stats["ai_performance"]["response_count"]
            },
            "token_usage": {
                "total_tokens": stats["ai_performance"]["total_tokens"],
                "total_cost_usd": round(stats["ai_performance"]["total_cost"], 2),
                "avg_daily_tokens": stats["ai_performance"]["total_tokens"] // days if days > 0 else 0,
                "avg_daily_cost_usd": round(stats["ai_performance"]["total_cost"] / days, 2) if days > 0 else 0,
                "model_breakdown": {k: v["tokens"] for k, v in stats["ai_performance"]["by_model"].items()}
            },
            "conversions": {
                "total_inquiries": inquiries,
                "total_appointments": stats["conversions"]["bookings"],
                "conversion_rate": round((stats["conversions"]["bookings"] / inquiries) * 100, 1) if inquiries > 0 else 0,
                "avg_messages_to_booking": round(avg_messages_to_booking, 1),
                "new_clients_booked": len(new_client_booked_users_sorted),
                "new_clients_asked_not_booked": len(new_client_asked_not_booked_users)
            },
            "new_clients": {
                "total_new_clients": len(new_client_users),
                "booked_count": len(new_client_booked_users_sorted),
                "not_booked_count": len(new_client_not_booked_users),
                "asked_not_booked_count": len(new_client_asked_not_booked_users),
                "booked_users": new_client_booked_users_sorted,
                "not_booked_users": new_client_not_booked_users,
                "asked_not_booked_users": new_client_asked_not_booked_users,
                "booked_details": booked_details,
                "not_booked_details": not_booked_details,
                "asked_not_booked_details": asked_not_booked_details
            },
            "services_discussed_today": {
                "date": services_today_metrics["date"],
                "total_mentions": sum(services_today_metrics["mentions_by_service"].values()),
                "unique_clients": len(services_today_metrics["all_users"]),
                "by_service": services_discussed_today
            },
            "time_range": {
                "start_date": (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(),
                "end_date": datetime.datetime.now().isoformat(),
                "days": days
            }
        }


# Global instance
analytics = AnalyticsEvents()
