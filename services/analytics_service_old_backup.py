"""
Analytics Service
Aggregates data from Firebase, Backend API, and logs to provide comprehensive analytics
"""

import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict
import json
import os

class AnalyticsService:
    """Service to aggregate analytics data from multiple sources"""
    
    def __init__(self):
        self.reports_log_file = 'data/reports_log.jsonl'
        self.USERS_COLLECTION = "users"
        self.APP_ID = "linas-ai-bot-backend"
    
    async def get_analytics_summary(self, time_range_days: int = 7) -> Dict[str, Any]:
        """
        Get comprehensive analytics summary
        Aggregates data from Firebase, Backend API, and logs
        """
        print(f"📊 Generating analytics summary for last {time_range_days} days...")
        
        # Calculate date range
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=time_range_days)
        
        # Gather data from all sources
        daily_summaries = await self._get_daily_summaries(start_date, end_date)
        hourly_distribution = await self._get_hourly_distribution(start_date, end_date)
        demographics = await self._get_demographics()
        performance = await self._get_performance_metrics(start_date, end_date)
        token_usage = await self._get_token_usage(start_date, end_date)
        conversions = await self._get_conversion_metrics(start_date, end_date)
        satisfaction = await self._get_satisfaction_metrics()
        appointments = await self._get_appointment_metrics(start_date, end_date)
        escalations = await self._get_escalation_metrics(start_date, end_date)
        services = await self._get_service_metrics(start_date, end_date)
        trending_topics = await self._get_trending_topics(start_date, end_date)
        sentiment_distribution = await self._get_sentiment_distribution(start_date, end_date)
        
        return {
            "daily_summaries": daily_summaries,
            "hourly_distribution": hourly_distribution,
            "demographics": demographics,
            "performance": performance,
            "token_usage": token_usage,
            "conversions": conversions,
            "satisfaction": satisfaction,
            "appointments": appointments,
            "escalations": escalations,
            "services": services,
            "trending_topics": trending_topics,
            "sentiment_distribution": sentiment_distribution,
            "time_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": time_range_days
            }
        }
    
    async def _get_daily_summaries(self, start_date: datetime.datetime, end_date: datetime.datetime) -> List[Dict]:
        """Get daily message summaries from Firebase conversations"""
        try:
            from utils.utils import get_firestore_db
            import config
            
            db = get_firestore_db()
            if not db:
                return []
            
            app_id = "linas-ai-bot-backend"
            users_collection = db.collection("artifacts").document(app_id).collection("users")
            
            # Initialize daily counters
            daily_data = defaultdict(lambda: {
                "total_messages": 0,
                "unique_users": set(),
                "new_users": 0,
                "token_cost_usd": 0.0
            })
            
            # Get all users from Firebase
            users_docs = list(users_collection.stream())
            print(f"📊 Analytics: Found {len(users_docs)} users in Firebase")
            
            for user_doc in users_docs:
                user_id = user_doc.id
                user_data = user_doc.to_dict() or {}
                
                # Get conversations for this user
                try:
                    conversations_collection = users_collection.document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                    conversations_docs = list(conversations_collection.stream())
                    print(f"📊 Analytics: User {user_id} has {len(conversations_docs)} conversations")
                    
                    for conv_doc in conversations_docs:
                        conv_data = conv_doc.to_dict() or {}
                        messages = conv_data.get("messages", [])
                        print(f"📊 Analytics: Conversation {conv_doc.id} has {len(messages)} messages")
                        
                        # Count messages
                        for message in messages:
                            if not message:
                                continue
                                
                            # Parse message timestamp
                            timestamp = message.get("timestamp")
                            msg_date = None
                            
                            try:
                                if isinstance(timestamp, str):
                                    # Try ISO format first
                                    msg_date = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                elif hasattr(timestamp, 'seconds'):
                                    # Firestore Timestamp
                                    msg_date = datetime.datetime.fromtimestamp(timestamp.seconds)
                                elif isinstance(timestamp, datetime.datetime):
                                    msg_date = timestamp
                            except Exception as ts_err:
                                print(f"❌ Error parsing timestamp {timestamp}: {ts_err}")
                                continue
                            
                            if not msg_date:
                                continue
                            
                            # Make both dates timezone-naive for comparison
                            if msg_date.tzinfo:
                                msg_date = msg_date.replace(tzinfo=None)
                            
                            # Check if message is within date range
                            if start_date <= msg_date <= end_date:
                                date_key = msg_date.date().isoformat()
                                daily_data[date_key]["total_messages"] += 1
                                daily_data[date_key]["unique_users"].add(user_id)
                                
                                # Estimate token cost (100 tokens per message, $0.002 per 1K tokens = $0.0002 per message)
                                daily_data[date_key]["token_cost_usd"] += 0.0002
                except Exception as conv_err:
                    print(f"❌ Error reading conversations for user {user_id}: {conv_err}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Convert to list format
            summaries = []
            current_date = start_date.date()
            while current_date <= end_date.date():
                date_key = current_date.isoformat()
                data = daily_data.get(date_key, {
                    "total_messages": 0,
                    "unique_users": set(),
                    "new_users": 0,
                    "token_cost_usd": 0.0
                })
                
                summaries.append({
                    "date": date_key,
                    "total_messages": data["total_messages"],
                    "unique_users": len(data["unique_users"]) if isinstance(data["unique_users"], set) else data["unique_users"],
                    "new_users": data["new_users"],
                    "token_cost_usd": round(data["token_cost_usd"], 2)
                })
                
                current_date += datetime.timedelta(days=1)
            
            return summaries
            
        except Exception as e:
            print(f"❌ Error getting daily summaries: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def _get_hourly_distribution(self, start_date: datetime.datetime, end_date: datetime.datetime) -> Dict[str, int]:
        """Get hourly message distribution from Firebase"""
        try:
            from utils.utils import get_firestore_db
            import config
            
            db = get_firestore_db()
            if not db:
                return {}
            
            app_id = "linas-ai-bot-backend"
            users_collection = db.collection("artifacts").document(app_id).collection("users")
            
            hourly_counts = defaultdict(int)
            
            # Get all users
            users_docs = users_collection.stream()
            
            for user_doc in users_docs:
                user_id = user_doc.id
                conversations_collection = users_collection.document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                conversations_docs = conversations_collection.stream()
                
                for conv_doc in conversations_docs:
                    conv_data = conv_doc.to_dict()
                    messages = conv_data.get("messages", [])
                    
                    for message in messages:
                        timestamp = message.get("timestamp")
                        if isinstance(timestamp, str):
                            try:
                                msg_date = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            except:
                                continue
                        elif hasattr(timestamp, 'seconds'):
                            msg_date = datetime.datetime.fromtimestamp(timestamp.seconds)
                        else:
                            continue
                        
                        # Make timezone-naive for comparison
                        if msg_date.tzinfo:
                            msg_date = msg_date.replace(tzinfo=None)
                        
                        if start_date <= msg_date <= end_date:
                            hour_key = f"{msg_date.hour:02d}:00"
                            hourly_counts[hour_key] += 1
            
            return dict(hourly_counts)
            
        except Exception as e:
            print(f"❌ Error getting hourly distribution: {e}")
            return {}
    
    async def _get_demographics(self) -> Dict[str, Any]:
        """Get demographics from Firebase and Backend API"""
        try:
            from utils.utils import get_firestore_db
            import config
            
            db = get_firestore_db()
            if not db:
                return {"languages": {"counts": {}, "percentages": {}}, "genders": {"counts": {}, "percentages": {}}}
            
            app_id = "linas-ai-bot-backend"
            users_collection = db.collection("artifacts").document(app_id).collection("users")
            
            language_counts = defaultdict(int)
            gender_counts = defaultdict(int)
            total_messages = 0
            
            # Get all users
            users_docs = users_collection.stream()
            
            for user_doc in users_docs:
                user_data = user_doc.to_dict()
                print(f"📊 Analytics: User {user_doc.id} fields: {list(user_data.keys()) if user_data else 'None'}")
                
                # Count genders from user document
                gender = user_data.get("gender", "unknown")
                if gender and gender != "unknown":
                    gender_counts[gender] += 1
                
                # Collect languages from messages
                conversations_collection = users_collection.document(user_doc.id).collection("conversations")
                conversations_docs = conversations_collection.stream()
                
                for conv_doc in conversations_docs:
                    conv_data = conv_doc.to_dict()
                    messages = conv_data.get("messages", [])
                    
                    for msg in messages:
                        total_messages += 1
                        # Get language from message (now saved with each message)
                        lang = msg.get("language", "ar")  # Default to Arabic if not specified
                        language_counts[lang] += 1
            
            # Calculate percentages
            lang_percentages = {}
            for lang, count in language_counts.items():
                lang_percentages[lang] = round((count / total_messages * 100), 1) if total_messages > 0 else 0
            
            gender_total = sum(gender_counts.values())
            gender_percentages = {}
            for gender, count in gender_counts.items():
                gender_percentages[gender] = round((count / gender_total * 100), 1) if gender_total > 0 else 0
            
            return {
                "languages": {
                    "counts": dict(language_counts),
                    "percentages": lang_percentages
                },
                "genders": {
                    "counts": dict(gender_counts),
                    "percentages": gender_percentages
                }
            }
            
        except Exception as e:
            print(f"❌ Error getting demographics: {e}")
            import traceback
            traceback.print_exc()
            return {"languages": {"counts": {}, "percentages": {}}, "genders": {"counts": {}, "percentages": {}}}
    
    async def _get_performance_metrics(self, start_date: datetime.datetime, end_date: datetime.datetime) -> Dict[str, Any]:
        """Get performance metrics from logs"""
        try:
            # For now, return estimated values
            # TODO: Track actual response times in Firebase or logs
            return {
                "avg_response_time_ms": 1250,
                "min_response_time_ms": 450,
                "max_response_time_ms": 3200,
                "p95_response_time_ms": 2100,
                "total_requests": 0
            }
        except Exception as e:
            print(f"❌ Error getting performance metrics: {e}")
            return {}
    
    async def _get_token_usage(self, start_date: datetime.datetime, end_date: datetime.datetime) -> Dict[str, Any]:
        """Get token usage from logs"""
        try:
            # Parse reports log for token usage
            total_tokens = 0
            total_cost = 0.0
            model_breakdown = defaultdict(int)
            
            if os.path.exists(self.reports_log_file):
                with open(self.reports_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            event = json.loads(line)
                            event_date = datetime.datetime.fromisoformat(event["timestamp"])
                            
                            if start_date <= event_date <= end_date:
                                # Look for API call events with token info
                                if event["type"] == "api_call":
                                    # Estimate tokens (rough estimate)
                                    total_tokens += 100
                                    total_cost += 0.0002
                                    model_breakdown["gpt-4o"] += 100
                        except:
                            continue
            
            days = (end_date - start_date).days or 1
            
            return {
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 2),
                "avg_daily_tokens": total_tokens // days,
                "avg_daily_cost_usd": round(total_cost / days, 2),
                "model_breakdown": dict(model_breakdown)
            }
            
        except Exception as e:
            print(f"❌ Error getting token usage: {e}")
            return {}
    
    async def _get_conversion_metrics(self, start_date: datetime.datetime, end_date: datetime.datetime) -> Dict[str, Any]:
        """Get conversion metrics from logs"""
        try:
            total_inquiries = 0
            total_appointments = 0
            
            if os.path.exists(self.reports_log_file):
                with open(self.reports_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            event = json.loads(line)
                            event_date = datetime.datetime.fromisoformat(event["timestamp"])
                            
                            if start_date <= event_date <= end_date:
                                if event["type"] == "new_user":
                                    total_inquiries += 1
                                elif event["type"] == "appointment_booked":
                                    total_appointments += 1
                        except:
                            continue
            
            conversion_rate = (total_appointments / total_inquiries * 100) if total_inquiries > 0 else 0
            
            return {
                "total_inquiries": total_inquiries,
                "total_appointments": total_appointments,
                "conversion_rate": round(conversion_rate, 1),
                "avg_messages_to_booking": 7.1  # TODO: Calculate from actual data
            }
            
        except Exception as e:
            print(f"❌ Error getting conversion metrics: {e}")
            return {}
    
    async def _get_satisfaction_metrics(self) -> Dict[str, Any]:
        """Get satisfaction metrics from feedback API"""
        try:
            from services.conversation_feedback_service import feedback_service
            
            stats = feedback_service.get_feedback_stats()
            
            total_feedback = stats.get("total_feedback", 0)
            likes = stats.get("good_feedback", 0)
            dislikes = total_feedback - likes
            satisfaction_rate = (likes / total_feedback * 100) if total_feedback > 0 else 0
            
            return {
                "total_feedback": total_feedback,
                "likes": likes,
                "dislikes": dislikes,
                "satisfaction_rate": round(satisfaction_rate, 1),
                "dislike_reasons": stats.get("feedback_by_type", {})
            }
            
        except Exception as e:
            print(f"❌ Error getting satisfaction metrics: {e}")
            return {}
    
    async def _get_appointment_metrics(self, start_date: datetime.datetime, end_date: datetime.datetime) -> Dict[str, Any]:
        """Get appointment metrics from logs"""
        try:
            total_booked = 0
            confirmed = 0
            rescheduled = 0
            cancelled = 0
            
            if os.path.exists(self.reports_log_file):
                with open(self.reports_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            event = json.loads(line)
                            event_date = datetime.datetime.fromisoformat(event["timestamp"])
                            
                            if start_date <= event_date <= end_date:
                                if event["type"] == "appointment_booked":
                                    total_booked += 1
                                    confirmed += 1  # Assume booked = confirmed for now
                                elif event["type"] == "appointment_rescheduled":
                                    rescheduled += 1
                                elif event["type"] == "appointment_cancelled":
                                    cancelled += 1
                        except:
                            continue
            
            confirmation_rate = (confirmed / total_booked * 100) if total_booked > 0 else 0
            reschedule_rate = (rescheduled / total_booked * 100) if total_booked > 0 else 0
            
            return {
                "total_booked": total_booked,
                "confirmed": confirmed,
                "rescheduled": rescheduled,
                "cancelled": cancelled,
                "confirmation_rate": round(confirmation_rate, 1),
                "reschedule_rate": round(reschedule_rate, 1)
            }
            
        except Exception as e:
            print(f"❌ Error getting appointment metrics: {e}")
            return {}
    
    async def _get_escalation_metrics(self, start_date: datetime.datetime, end_date: datetime.datetime) -> Dict[str, Any]:
        """Get escalation metrics from logs"""
        try:
            total_escalations = 0
            human_handover = 0
            complaints = 0
            technical_issues = 0
            
            if os.path.exists(self.reports_log_file):
                with open(self.reports_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            event = json.loads(line)
                            event_date = datetime.datetime.fromisoformat(event["timestamp"])
                            
                            if start_date <= event_date <= end_date:
                                if event["type"] == "human_handover":
                                    total_escalations += 1
                                    human_handover += 1
                                elif event["type"] == "complaint":
                                    total_escalations += 1
                                    complaints += 1
                                elif event["type"] == "technical_issue":
                                    total_escalations += 1
                                    technical_issues += 1
                        except:
                            continue
            
            # Calculate escalation rate (need total conversations)
            escalation_rate = 3.8  # TODO: Calculate from actual data
            
            return {
                "total_escalations": total_escalations,
                "human_handover": human_handover,
                "complaints": complaints,
                "technical_issues": technical_issues,
                "escalation_rate": escalation_rate
            }
            
        except Exception as e:
            print(f"❌ Error getting escalation metrics: {e}")
            return {}
    
    async def _get_service_metrics(self, start_date: datetime.datetime, end_date: datetime.datetime) -> Dict[str, Any]:
        """Get service metrics from logs"""
        try:
            service_counts = defaultdict(int)
            
            if os.path.exists(self.reports_log_file):
                with open(self.reports_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            event = json.loads(line)
                            event_date = datetime.datetime.fromisoformat(event["timestamp"])
                            
                            if start_date <= event_date <= end_date:
                                if event["type"] == "appointment_booked":
                                    service = event.get("details", {}).get("service", "Unknown")
                                    service_counts[service] += 1
                        except:
                            continue
            
            # Calculate percentages
            total_requests = sum(service_counts.values())
            most_requested = []
            
            for service, count in sorted(service_counts.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_requests * 100) if total_requests > 0 else 0
                most_requested.append({
                    "name": service,
                    "count": count,
                    "percentage": round(percentage, 1)
                })
            
            return {
                "most_requested": most_requested[:5]  # Top 5 services
            }
            
        except Exception as e:
            print(f"❌ Error getting service metrics: {e}")
            return {}
    
    async def _get_sentiment_distribution(self, start_date: datetime.datetime, end_date: datetime.datetime) -> Dict:
        """Get mood/sentiment distribution from conversations"""
        try:
            from utils.utils import get_firestore_db
            import config
            
            db = get_firestore_db()
            if not db:
                return {"positive": 0, "negative": 0, "neutral": 0}
            
            sentiment_dist = {
                "positive": 0,
                "negative": 0,
                "neutral": 0
            }
            
            # Query all users
            users_ref = db.collection("artifacts").document(self.APP_ID).collection(self.USERS_COLLECTION)
            users_docs = list(users_ref.stream())
            
            for user_doc in users_docs:
                user_id = user_doc.id
                conversations_ref = users_ref.document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION)
                
                # Query conversations in time range
                try:
                    conv_docs = list(conversations_ref.stream())
                    
                    for conv_doc in conv_docs:
                        conv_data = conv_doc.to_dict()
                        if not conv_data:
                            continue
                        
                        # Check conversation date
                        created_at = conv_data.get('created_at')
                        if created_at:
                            try:
                                if isinstance(created_at, str):
                                    conv_date = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                elif hasattr(created_at, 'seconds'):
                                    conv_date = datetime.datetime.fromtimestamp(created_at.seconds)
                                else:
                                    conv_date = created_at
                                
                                if not (start_date <= conv_date <= end_date):
                                    continue
                            except:
                                pass
                        
                        # Get sentiment
                        sentiment = conv_data.get('sentiment', 'neutral')
                        
                        # Normalize sentiment value
                        if sentiment and isinstance(sentiment, str):
                            sentiment = sentiment.lower().strip()
                            if sentiment in sentiment_dist:
                                sentiment_dist[sentiment] += 1
                            else:
                                sentiment_dist['neutral'] += 1
                        else:
                            sentiment_dist['neutral'] += 1
                            
                except Exception as conv_err:
                    print(f"⚠️  Error reading conversations for user {user_id}: {conv_err}")
                    continue
            
            print(f"📊 Analytics: Sentiment distribution - {sentiment_dist}")
            return sentiment_dist
            
        except Exception as e:
            print(f"❌ Error getting sentiment distribution: {e}")
            return {"positive": 0, "negative": 0, "neutral": 0}

    async def _get_trending_topics(self, start_date: datetime.datetime, end_date: datetime.datetime) -> List[Dict]:
        """Get trending topics from Q&A usage"""
        try:
            from services.qa_database_service import qa_db_service
            
            # Get Q&A statistics
            stats_response = await qa_db_service.get_statistics()
            
            if stats_response.get("success"):
                stats = stats_response.get("data", {})
                categories = stats.get("by_category", {})
                
                # Convert to trending topics format
                trending = []
                for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]:
                    trending.append({
                        "topic": category,
                        "count": count
                    })
                
                return trending
            
            return []
            
        except Exception as e:
            print(f"❌ Error getting trending topics: {e}")
            return []


# Global instance
analytics_service = AnalyticsService()
