"""AnalyticsEvents aggregation (LOC split)."""

from __future__ import annotations

import datetime
import json
import os
from collections import defaultdict
from typing import Any


class AnalyticsEventsAggregateMixin:
    """Read events and aggregate analytics stats."""

    def get_events(self, days: int | None = 7, event_type: str | None = None) -> list[dict[str, Any]]:
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

            with open(self.events_file, encoding="utf-8") as f:
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
                    except Exception:
                        continue

            return events

        except Exception as e:
            print(f"❌ Error reading events: {e}")
            return []

    def aggregate_analytics(self, days: int = 7) -> dict[str, Any]:
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
            first_seen_by_user: dict[str, datetime.datetime] = {}
            for event in all_events:
                user_id = self._normalize_user_id(event.get("user_id"))
                event_dt = self._parse_timestamp(event.get("timestamp"))
                if not user_id or not event_dt:
                    continue
                existing_first_seen = first_seen_by_user.get(user_id)
                if existing_first_seen is None or event_dt < existing_first_seen:
                    first_seen_by_user[user_id] = event_dt

            # Initialize counters
            stats: dict[str, Any] = {
                "overview": {
                    "total_messages": 0,
                    "total_conversations": 0,
                    "unique_users": set(),
                    "new_users": 0,
                    "active_user_message_users": set(),
                },
                "messages": {
                    "by_type": defaultdict(int),
                    "by_source": defaultdict(int),
                    "by_language": defaultdict(int),
                    "daily": defaultdict(lambda: defaultdict(int)),
                    "hourly": defaultdict(int),
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
                    "by_service": defaultdict(lambda: defaultdict(int)),
                },
                "feedback": {"total": 0, "likes": 0, "dislikes": 0, "reasons": defaultdict(int)},
                "session_ratings": {
                    "by_star": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                    "total": 0,
                    "sum_stars": 0,
                    "rated_users": set(),
                },
                "pause_cleared": {
                    "total": 0,
                    "unique_users": set(),
                    "events": [],
                    "by_service_counts": defaultdict(int),
                    "by_service_unique_users": defaultdict(set),
                },
                "smart_reminders": {
                    "sent": [],
                    "replies": [],
                },
                "appointment_reschedules": [],
                "escalations": {
                    "total": 0,
                    "by_type": defaultdict(int),
                    "human_handover_users": set(),
                },
                "ai_performance": {
                    "total_response_time": 0,
                    "response_count": 0,
                    "min_response_time": None,
                    "max_response_time": None,
                    "response_times": [],
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "by_model": defaultdict(lambda: {"tokens": 0, "cost": 0.0}),
                },
                "conversions": {
                    "inquiries": 0,
                    "qualified_leads": 0,
                    "appointment_requests": 0,
                    "bookings": 0,
                    "messages_to_booking": [],
                    "inquiry_users": set(),
                },
                "new_client_metrics": {
                    "all_new_users": set(),
                    "asked_users": set(),
                    "booked_users": set(),
                    "services_by_user": defaultdict(set),
                    "booked_services_by_user": defaultdict(set),
                },
                "services_today": {
                    "date": today_date.isoformat(),
                    "mentions_by_service": defaultdict(int),
                    "users_by_service": defaultdict(set),
                    "all_users": set(),
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
                    if first_seen and range_start <= first_seen <= now and not self._is_test_user_id(user_id):
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
                    source = event.get("source", "user")
                    stats["messages"]["by_source"][source] += 1
                    # Language demographics count user messages only (not bot echoes)
                    if source == "user":
                        stats["messages"]["by_language"][event.get("language", "ar")] += 1

                    # Only count explicitly labeled sentiments (ignore placeholder "neutral" defaults)
                    sentiment = event.get("sentiment")
                    if sentiment and sentiment in {"positive", "negative"}:
                        stats["sentiment"][sentiment] += 1
                    elif sentiment == "neutral" and event.get("sentiment_detected") is True:
                        stats["sentiment"]["neutral"] += 1

                    # Time-based
                    if date_key:
                        stats["messages"]["daily"][date_key]["total"] += 1
                        stats["messages"]["daily"][date_key][event.get("msg_type", "text")] += 1
                        if source == "user":
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
                    if (
                        user_id
                        and user_id in stats["new_client_metrics"]["all_new_users"]
                        and not self._is_test_user_id(user_id)
                    ):
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
                        if (
                            user_id
                            and user_id in stats["new_client_metrics"]["all_new_users"]
                            and not self._is_test_user_id(user_id)
                        ):
                            stats["new_client_metrics"]["booked_users"].add(user_id)
                            if service:
                                stats["new_client_metrics"]["booked_services_by_user"][user_id].add(service)
                    elif status == "confirmed":
                        stats["appointments"]["confirmed"] += 1
                    elif status == "rescheduled":
                        stats["appointments"]["rescheduled"] += 1
                        stats["appointment_reschedules"].append(
                            {
                                "user_id": user_id,
                                "service": service,
                                "at": event.get("timestamp"),
                                "phone": event.get("phone"),
                                "appointment_id": event.get("appointment_id"),
                            }
                        )
                    elif status == "cancelled":
                        stats["appointments"]["cancelled"] += 1

                    if service and status:
                        stats["appointments"]["by_service"][service][status] += 1

                elif event_type == "feedback":
                    stats["feedback"]["total"] += 1
                    feedback_type = str(event.get("feedback_type") or "").strip().lower()
                    like_types = {"good", "like", "likes", "positive", "up", "thumbs_up", "👍"}
                    dislike_types = {
                        "wrong",
                        "bad",
                        "dislike",
                        "dislikes",
                        "negative",
                        "down",
                        "thumbs_down",
                        "inappropriate",
                        "unclear",
                        "👎",
                    }
                    if feedback_type in like_types:
                        stats["feedback"]["likes"] += 1
                    elif feedback_type in dislike_types or feedback_type:
                        stats["feedback"]["dislikes"] += 1
                        reason = event.get("reason", feedback_type)
                        if reason:
                            stats["feedback"]["reasons"][reason] += 1

                elif event_type == "session_rating":
                    stars = max(1, min(5, self._safe_int(event.get("stars"))))
                    sr = stats["session_ratings"]
                    sr["by_star"][stars] = sr["by_star"].get(stars, 0) + 1
                    sr["total"] += 1
                    sr["sum_stars"] += stars
                    if user_id:
                        sr["rated_users"].add(user_id)

                elif event_type == "appointment_pause_cleared":
                    pc = stats["pause_cleared"]
                    pc["total"] += 1
                    if user_id:
                        pc["unique_users"].add(user_id)
                    svc_key = str(event.get("service") or "unknown").strip() or "unknown"
                    pc["by_service_counts"][svc_key] += 1
                    if user_id:
                        pc["by_service_unique_users"][svc_key].add(user_id)
                    aid = event.get("appointment_id")
                    pc["events"].append(
                        {
                            "user_id": user_id,
                            "appointment_id": aid,
                            "phone": event.get("phone"),
                            "service": event.get("service"),
                            "at": event.get("timestamp"),
                        }
                    )

                elif event_type == "smart_reminder_sent":
                    sm = stats["smart_reminders"]
                    sm["sent"].append(
                        {
                            "user_id": user_id,
                            "message_id": event.get("message_id"),
                            "template_id": event.get("template_id") or "reminder_24h",
                            "appointment_id": event.get("appointment_id"),
                            "phone": event.get("phone"),
                            "appointment_at": event.get("appointment_at"),
                            "at": event.get("timestamp"),
                        }
                    )

                elif event_type == "smart_reminder_reply":
                    sm = stats["smart_reminders"]
                    sm["replies"].append(
                        {
                            "user_id": user_id,
                            "intent": event.get("intent"),
                            "source_message_id": event.get("source_message_id"),
                            "appointment_id": event.get("appointment_id"),
                            "phone": event.get("phone"),
                            "at": event.get("timestamp"),
                        }
                    )

                elif event_type == "escalation":
                    stats["escalations"]["total"] += 1
                    escalation_type = event.get("escalation_type")
                    if escalation_type:
                        stats["escalations"]["by_type"][escalation_type] += 1
                    if escalation_type == "human_handover" and user_id:
                        stats["escalations"]["human_handover_users"].add(user_id)

            # Normalize counters and fallback values.
            stats["conversions"]["inquiries"] = len(stats["conversions"]["inquiry_users"])
            if stats["overview"]["total_conversations"] == 0:
                stats["overview"]["total_conversations"] = len(stats["overview"]["active_user_message_users"])
            if stats["overview"]["new_users"] == 0:
                stats["overview"]["new_users"] = len(stats["new_client_metrics"]["all_new_users"])

            # Convert sets to counts
            stats["overview"]["unique_users"] = len(stats["overview"]["unique_users"])
            # All-time distinct users who ever appear in analytics (not limited to selected days).
            stats["lifetime_unique_users"] = len(first_seen_by_user)
            stats["latest_session_rating_by_user"] = self._latest_session_rating_by_user(events)
            pc_events = stats["pause_cleared"]["events"]

            def _pause_at(row: dict[str, Any]) -> datetime.datetime:
                t = self._parse_timestamp(row.get("at"))
                return t if t else datetime.datetime.min

            pc_events.sort(key=_pause_at, reverse=True)
            stats["pause_cleared"]["events"] = pc_events[:80]

            sm = stats.get("smart_reminders") or {"sent": [], "replies": []}

            def _row_at(row: dict[str, Any]) -> datetime.datetime:
                t = self._parse_timestamp(row.get("at"))
                return t if t else datetime.datetime.min

            sm["sent"].sort(key=_row_at, reverse=True)
            sm["sent"] = sm["sent"][:120]
            sm["replies"].sort(key=_row_at, reverse=True)
            sm["replies"] = sm["replies"][:120]
            stats["smart_reminders"] = sm

            ar_list = stats.get("appointment_reschedules") or []
            ar_list.sort(key=lambda row: _row_at(row), reverse=True)
            stats["appointment_reschedules"] = ar_list[:80]

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
