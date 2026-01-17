# -*- coding: utf-8 -*-
"""
Analytics Events System
Simple append-only event logging for analytics
Each event is one line in a JSONL file
"""

import json
import os
import datetime
from typing import Dict, Any, List
from collections import defaultdict


class AnalyticsEvents:
    """Handles analytics event logging and aggregation"""
    
    def __init__(self):
        self.events_file = "data/analytics_events.jsonl"
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
    
    # ==================== AGGREGATION METHODS ====================
    
    def get_events(self, days: int = 7, event_type: str = None) -> List[Dict[str, Any]]:
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
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
            
            if not os.path.exists(self.events_file):
                return []
            
            with open(self.events_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        event_date = datetime.datetime.fromisoformat(event["timestamp"])
                        
                        # Filter by date
                        if event_date >= cutoff_date:
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
            events = self.get_events(days=days)
            
            # Initialize counters
            stats = {
                "overview": {
                    "total_messages": 0,
                    "total_conversations": 0,
                    "unique_users": set(),
                    "new_users": 0
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
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "by_model": defaultdict(lambda: {"tokens": 0, "cost": 0.0})
                },
                "conversions": {
                    "inquiries": 0,
                    "qualified_leads": 0,
                    "appointment_requests": 0,
                    "bookings": 0,
                    "messages_to_booking": []
                }
            }
            
            # Process each event
            for event in events:
                event_type = event.get("type")
                user_id = event.get("user_id")
                timestamp = event.get("timestamp")
                
                # Track unique users
                if user_id:
                    stats["overview"]["unique_users"].add(user_id)
                
                # Parse timestamp for time-based stats
                try:
                    dt = datetime.datetime.fromisoformat(timestamp)
                    date_key = dt.strftime("%Y-%m-%d")
                    hour_key = f"{dt.hour:02d}:00"
                except:
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
                        response_time = event.get("response_time_ms")
                        if response_time:
                            stats["ai_performance"]["total_response_time"] += response_time
                            stats["ai_performance"]["response_count"] += 1
                            
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
                        
                        tokens = event.get("tokens", 0)
                        cost = event.get("cost_usd", 0.0)
                        model = event.get("model", "unknown")
                        
                        if tokens > 0:
                            stats["ai_performance"]["total_tokens"] += tokens
                            stats["ai_performance"]["by_model"][model]["tokens"] += tokens
                        
                        if cost > 0:
                            stats["ai_performance"]["total_cost"] += cost
                            stats["ai_performance"]["by_model"][model]["cost"] += cost
                
                elif event_type == "conversation_start":
                    stats["overview"]["total_conversations"] += 1
                    stats["conversions"]["inquiries"] += 1
                    if event.get("is_new_user"):
                        stats["overview"]["new_users"] += 1
                
                elif event_type == "gender":
                    gender = event.get("gender")
                    if gender:
                        stats["genders"][gender] += 1
                
                elif event_type == "service_request":
                    service = event.get("service")
                    if service:
                        stats["services"][service] += 1
                        stats["conversions"]["qualified_leads"] += 1
                
                elif event_type == "appointment":
                    status = event.get("status")
                    service = event.get("service")
                    
                    if status == "requested":
                        stats["appointments"]["requested"] += 1
                        stats["conversions"]["appointment_requests"] += 1
                    elif status == "booked":
                        stats["appointments"]["booked"] += 1
                        stats["conversions"]["bookings"] += 1
                        
                        messages_count = event.get("messages_count", 0)
                        if messages_count > 0:
                            stats["conversions"]["messages_to_booking"].append(messages_count)
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
            
            # Convert sets to counts
            stats["overview"]["unique_users"] = len(stats["overview"]["unique_users"])
            
            # Build final response
            return self._format_analytics_response(stats, days)
            
        except Exception as e:
            print(f"❌ Error aggregating analytics: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def _format_analytics_response(self, stats: Dict, days: int) -> Dict[str, Any]:
        """Format aggregated stats into API response"""
        
        # Calculate rates and percentages
        total_messages = stats["overview"]["total_messages"]
        total_booked = stats["appointments"]["booked"]
        total_feedback = stats["feedback"]["total"]
        inquiries = stats["conversions"]["inquiries"]
        
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
        
        return {
            "success": True,
            "overview": {
                "total_messages": total_messages,
                "total_conversations": stats["overview"]["total_conversations"],
                "total_users": stats["overview"]["unique_users"],
                "new_users": stats["overview"]["new_users"],
                "returning_users": stats["overview"]["unique_users"] - stats["overview"]["new_users"]
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
                "most_requested": service_list[:10]
            },
            "appointments": {
                "total_booked": total_booked,
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
                "p95_response_time_ms": 0,
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
                "avg_messages_to_booking": round(avg_messages_to_booking, 1)
            },
            "time_range": {
                "start_date": (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(),
                "end_date": datetime.datetime.now().isoformat(),
                "days": days
            }
        }


# Global instance
analytics = AnalyticsEvents()
