"""AnalyticsEvents response formatting (LOC split)."""

from __future__ import annotations

import datetime
import math
import re
from collections import defaultdict
from typing import Any


class AnalyticsEventsFormatMixin:
    """Shape aggregate stats into the dashboard analytics payload."""

    def _format_analytics_response(self, stats: dict, days: int) -> dict[str, Any]:
        """Format aggregated stats into API response"""

        # Calculate rates and percentages
        total_messages = stats["overview"]["total_messages"]
        total_conversations = stats["overview"]["total_conversations"]
        total_booked = stats["appointments"]["booked"]
        # Denominator for status shares: all appointment lifecycle events (not "of booked only" —
        # reschedules can exceed bookings in a period and would break % vs booked).
        appt_events_total = (
            stats["appointments"]["requested"]
            + stats["appointments"]["booked"]
            + stats["appointments"]["confirmed"]
            + stats["appointments"]["rescheduled"]
            + stats["appointments"]["cancelled"]
        )
        total_feedback = stats["feedback"]["total"]
        sr = stats["session_ratings"]
        sr_total = sr["total"]
        sr_by_star = {str(k): int(sr["by_star"].get(k, 0)) for k in (1, 2, 3, 4, 5)}
        sr_avg = round(sr["sum_stars"] / sr_total, 2) if sr_total > 0 else 0
        sr_unique = len(sr["rated_users"])
        sr_pct = {
            str(k): round((sr["by_star"].get(k, 0) / sr_total) * 100, 1) if sr_total > 0 else 0 for k in (1, 2, 3, 4, 5)
        }
        inquiries = stats["conversions"]["inquiries"]
        total_users = stats["overview"]["unique_users"]
        new_users = stats["overview"]["new_users"]
        lifetime_unique_users = stats.get("lifetime_unique_users", 0)

        avg_messages_per_day = round((total_messages / days), 1) if days > 0 else 0
        avg_messages_per_conversation = (
            round((total_messages / total_conversations), 1) if total_conversations > 0 else 0
        )

        # Build daily summaries
        daily_summaries = []
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=days)
        current_date = start_date.date()

        while current_date <= end_date.date():
            date_key = current_date.strftime("%Y-%m-%d")
            day_data = stats["messages"]["daily"].get(date_key, {})

            daily_summaries.append(
                {
                    "date": date_key,
                    "total_messages": day_data.get("total", 0),
                    "text_messages": day_data.get("text", 0),
                    "voice_messages": day_data.get("voice", 0),
                    "image_messages": day_data.get("image", 0),
                    "language_ar": day_data.get("ar", 0),
                    "language_en": day_data.get("en", 0),
                    "language_fr": day_data.get("fr", 0),
                    "language_franco": day_data.get("franco", 0),
                }
            )

            current_date += datetime.timedelta(days=1)

        # Calculate percentages
        def calc_percentages(counts_dict: dict[Any, Any]) -> dict[Any, float]:
            total = sum(counts_dict.values())
            if total == 0:
                return {}
            return {k: round((v / total) * 100, 1) for k, v in counts_dict.items()}

        # Build service list
        service_list = []
        total_service_requests = sum(stats["services"].values())
        for service, count in sorted(stats["services"].items(), key=lambda x: x[1], reverse=True):
            percentage = round((count / total_service_requests) * 100, 1) if total_service_requests > 0 else 0
            service_list.append({"name": service, "count": count, "percentage": percentage})

        # Bookings per service (appointment events with status "booked" only)
        booked_by_service: dict[str, int] = {}
        for svc, status_map in stats["appointments"]["by_service"].items():
            n = int(status_map.get("booked", 0))
            if n:
                booked_by_service[str(svc)] = n
        total_booked_service_events = sum(booked_by_service.values())
        most_booked_list = []
        for service, count in sorted(booked_by_service.items(), key=lambda x: x[1], reverse=True):
            pct = round((count / total_booked_service_events) * 100, 1) if total_booked_service_events > 0 else 0
            most_booked_list.append({"name": service, "count": count, "percentage": pct})

        # Calculate averages
        avg_response_time = 0
        if stats["ai_performance"]["response_count"] > 0:
            avg_response_time = (
                stats["ai_performance"]["total_response_time"] / stats["ai_performance"]["response_count"]
            )

        avg_messages_to_booking = 0
        if stats["conversions"]["messages_to_booking"]:
            avg_messages_to_booking = sum(stats["conversions"]["messages_to_booking"]) / len(
                stats["conversions"]["messages_to_booking"]
            )

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
            booked_details.append(
                {
                    "user_id": user_id,
                    "user_id_masked": self._mask_user_id(user_id),
                    "services": sorted(discussed | booked),
                    "discussed_services": sorted(discussed),
                    "booked_services": sorted(booked),
                }
            )

        not_booked_details = []
        for user_id in new_client_not_booked_users:
            discussed_services = sorted(new_client_metrics["services_by_user"].get(user_id, set()))
            not_booked_details.append(
                {"user_id": user_id, "user_id_masked": self._mask_user_id(user_id), "services": discussed_services}
            )

        asked_not_booked_details = []
        for user_id in new_client_asked_not_booked_users:
            discussed_services = sorted(new_client_metrics["services_by_user"].get(user_id, set()))
            asked_not_booked_details.append(
                {
                    "user_id": user_id,
                    "user_id_masked": self._mask_user_id(user_id),
                    "services": discussed_services,
                    "discussed_services": discussed_services,
                    "booked_services": [],
                }
            )

        # Services discussed today
        services_today_metrics = stats["services_today"]
        services_discussed_today = []
        for service, mentions in sorted(
            services_today_metrics["mentions_by_service"].items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            services_discussed_today.append(
                {
                    "service": service,
                    "mentions": mentions,
                    "unique_clients": len(services_today_metrics["users_by_service"].get(service, set())),
                }
            )

        latest_sr = stats.get("latest_session_rating_by_user") or {}
        pc_stats = stats.get("pause_cleared") or {}
        pc_unique = pc_stats.get("unique_users") or set()
        bs_counts = dict(pc_stats.get("by_service_counts") or {})
        bs_u = pc_stats.get("by_service_unique_users") or {}
        pause_by_service = []
        for svc, appt_n in sorted(bs_counts.items(), key=lambda x: (-x[1], x[0])):
            u_set = bs_u.get(svc)
            n_cust = len(u_set) if isinstance(u_set, set) else 0
            pause_by_service.append(
                {
                    "service": svc,
                    "appointments": appt_n,
                    "unique_customers": n_cust,
                }
            )
        pause_cleared_recent = []
        for row in pc_stats.get("events", []) or []:
            uid = row.get("user_id")
            phone_raw = row.get("phone") or ""
            digits = re.sub(r"\D", "", str(phone_raw))
            search_q = digits if digits else re.sub(r"\D", "", str(uid or ""))
            pause_cleared_recent.append(
                {
                    "user_id_masked": self._mask_user_id(uid),
                    "phone_masked": self._mask_phone_tail(str(phone_raw)) if phone_raw else "",
                    "appointment_id": row.get("appointment_id"),
                    "service": row.get("service"),
                    "at": row.get("at"),
                    "live_chat_search": search_q or str(uid or ""),
                    "last_session_rating_stars": latest_sr.get(uid) if uid else None,
                }
            )

        sm_stats = stats.get("smart_reminders") or {}
        sent_rows = list(sm_stats.get("sent") or [])
        reply_rows = list(sm_stats.get("replies") or [])

        def _live_chat_q(uid: Any, phone_raw: Any) -> str:
            phone_raw = phone_raw or ""
            digits = re.sub(r"\D", "", str(phone_raw))
            if digits:
                return digits
            return re.sub(r"\D", "", str(uid or "")) or str(uid or "")

        def _sent_has_reply(sent: dict[str, Any]) -> bool:
            mid = sent.get("message_id")
            if mid:
                mids = {str(r.get("source_message_id")) for r in reply_rows if r.get("source_message_id")}
                if str(mid) in mids:
                    return True
            uid = self._normalize_user_id(sent.get("user_id"))
            if not uid:
                return False
            st = self._parse_timestamp(sent.get("at"))
            said = sent.get("appointment_id")
            for r in reply_rows:
                if self._normalize_user_id(r.get("user_id")) != uid:
                    continue
                rt = self._parse_timestamp(r.get("at"))
                if not rt or not st or rt <= st:
                    continue
                rid = r.get("appointment_id")
                if said is not None and rid is not None:
                    try:
                        if int(said) == int(rid):
                            return True
                    except (TypeError, ValueError):
                        pass
                elif said is None and rid is None:
                    return True
            return False

        no_reply_count = 0
        no_reply_users = set()
        for s in sent_rows:
            if _sent_has_reply(s):
                continue
            uid = self._normalize_user_id(s.get("user_id"))
            no_reply_count += 1
            if uid:
                no_reply_users.add(uid)

        no_response_recent = []
        for s in sent_rows:
            if _sent_has_reply(s):
                continue
            uid = self._normalize_user_id(s.get("user_id"))
            if not uid:
                continue
            pr = s.get("phone") or ""
            q = _live_chat_q(uid, pr)
            no_response_recent.append(
                {
                    "user_id_masked": self._mask_user_id(uid),
                    "phone_masked": self._mask_phone_tail(str(pr)) if pr else "",
                    "appointment_id": s.get("appointment_id"),
                    "appointment_at": s.get("appointment_at"),
                    "sent_at": s.get("at"),
                    "live_chat_search": q or str(uid),
                    "last_session_rating_stars": latest_sr.get(uid) if uid else None,
                }
            )
        no_response_recent = no_response_recent[:60]

        reminder_reply_recent = []
        intent_counts: dict[str, int] = defaultdict(int)
        for r in reply_rows:
            intent = (r.get("intent") or "other").lower()
            intent_counts[intent] += 1
            uid = self._normalize_user_id(r.get("user_id"))
            if not uid:
                continue
            pr = r.get("phone") or ""
            q = _live_chat_q(uid, pr)
            reminder_reply_recent.append(
                {
                    "intent": intent,
                    "user_id_masked": self._mask_user_id(uid),
                    "phone_masked": self._mask_phone_tail(str(pr)) if pr else "",
                    "appointment_id": r.get("appointment_id"),
                    "at": r.get("at"),
                    "live_chat_search": q or str(uid),
                    "last_session_rating_stars": latest_sr.get(uid) if uid else None,
                }
            )
        reminder_reply_recent = reminder_reply_recent[:60]

        reschedule_recent = []
        for row in stats.get("appointment_reschedules") or []:
            uid = self._normalize_user_id(row.get("user_id"))
            if not uid:
                continue
            pr = row.get("phone") or ""
            q = _live_chat_q(uid, pr)
            reschedule_recent.append(
                {
                    "user_id_masked": self._mask_user_id(uid),
                    "phone_masked": self._mask_phone_tail(str(pr)) if pr else "",
                    "appointment_id": row.get("appointment_id"),
                    "service": row.get("service"),
                    "at": row.get("at"),
                    "live_chat_search": q or str(uid),
                    "last_session_rating_stars": latest_sr.get(uid) if uid else None,
                }
            )

        return {
            "success": True,
            "overview": {
                "total_messages": total_messages,
                "total_conversations": total_conversations,
                "total_users": total_users,
                "new_users": new_users,
                "returning_users": max(total_users - new_users, 0),
                "lifetime_unique_users": lifetime_unique_users,
                "avg_messages_per_day": avg_messages_per_day,
                "avg_messages_per_conversation": avg_messages_per_conversation,
            },
            "daily_summaries": daily_summaries,
            "hourly_distribution": dict(stats["messages"]["hourly"]),
            "demographics": {
                "languages": {
                    "counts": dict(stats["messages"]["by_language"]),
                    "percentages": calc_percentages(stats["messages"]["by_language"]),
                },
                "genders": {"counts": dict(stats["genders"]), "percentages": calc_percentages(stats["genders"])},
            },
            "sentiment_distribution": dict(stats["sentiment"]),
            "services": {
                "most_requested": service_list[:10],
                "most_booked": most_booked_list[:10],
                "discussed_today": services_discussed_today,
            },
            "appointments": {
                "total_booked": total_booked,
                "requested": stats["appointments"]["requested"],
                "confirmed": stats["appointments"]["confirmed"],
                "rescheduled": stats["appointments"]["rescheduled"],
                "cancelled": stats["appointments"]["cancelled"],
                "appointment_events_total": appt_events_total,
                "confirmation_rate": round((stats["appointments"]["confirmed"] / appt_events_total) * 100, 1)
                if appt_events_total > 0
                else 0,
                "reschedule_rate": round((stats["appointments"]["rescheduled"] / appt_events_total) * 100, 1)
                if appt_events_total > 0
                else 0,
                "cancellation_rate": round((stats["appointments"]["cancelled"] / appt_events_total) * 100, 1)
                if appt_events_total > 0
                else 0,
            },
            "satisfaction": {
                "total_feedback": total_feedback,
                "likes": stats["feedback"]["likes"],
                "dislikes": stats["feedback"]["dislikes"],
                "satisfaction_rate": round((stats["feedback"]["likes"] / total_feedback) * 100, 1)
                if total_feedback > 0
                else 0,
                "dislike_reasons": dict(stats["feedback"]["reasons"]),
            },
            "session_ratings": {
                "total_ratings": sr_total,
                "unique_raters": sr_unique,
                "average_stars": sr_avg,
                "by_star": sr_by_star,
                "percentages": sr_pct,
            },
            "pause_cleared_resumes": {
                "total": pc_stats.get("total", 0),
                "unique_users": len(pc_unique) if isinstance(pc_unique, set) else int(pc_unique or 0),
                "by_service": pause_by_service,
                "recent": pause_cleared_recent,
            },
            "smart_reminders": {
                "sent_total": len(sent_rows),
                "replies_total": len(reply_rows),
                "no_reply_to_reminder": {
                    "count": no_reply_count,
                    "unique_users": len(no_reply_users),
                },
                "reply_intents": dict(intent_counts),
                "no_response_recent": no_response_recent,
                "reminder_replies_recent": reminder_reply_recent,
            },
            "appointment_reschedules_detail": {
                "total": stats["appointments"]["rescheduled"],
                "recent": reschedule_recent,
            },
            "escalations": {
                "total_escalations": stats["escalations"]["total"],
                "human_handover": stats["escalations"]["by_type"].get("human_handover", 0),
                "human_handover_unique_users": len(stats["escalations"]["human_handover_users"]),
                "complaints": stats["escalations"]["by_type"].get("complaint", 0),
                "technical_issues": stats["escalations"]["by_type"].get("technical_issue", 0),
            },
            "performance": {
                "avg_response_time_ms": round(avg_response_time, 0),
                "min_response_time_ms": stats["ai_performance"]["min_response_time"] or 0,
                "max_response_time_ms": stats["ai_performance"]["max_response_time"] or 0,
                "p95_response_time_ms": round(p95_response_time, 0) if p95_response_time else 0,
                "total_requests": stats["ai_performance"]["response_count"],
            },
            "token_usage": {
                "total_tokens": stats["ai_performance"]["total_tokens"],
                "total_cost_usd": round(stats["ai_performance"]["total_cost"], 2),
                "avg_daily_tokens": stats["ai_performance"]["total_tokens"] // days if days > 0 else 0,
                "avg_daily_cost_usd": round(stats["ai_performance"]["total_cost"] / days, 2) if days > 0 else 0,
                "model_breakdown": {k: v["tokens"] for k, v in stats["ai_performance"]["by_model"].items()},
            },
            "conversions": {
                "total_inquiries": inquiries,
                "total_appointments": stats["conversions"]["bookings"],
                "conversion_rate": round((stats["conversions"]["bookings"] / inquiries) * 100, 1)
                if inquiries > 0
                else 0,
                "avg_messages_to_booking": round(avg_messages_to_booking, 1),
                "new_clients_booked": len(new_client_booked_users_sorted),
                "new_clients_asked_not_booked": len(new_client_asked_not_booked_users),
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
                "asked_not_booked_details": asked_not_booked_details,
            },
            "services_discussed_today": {
                "date": services_today_metrics["date"],
                "total_mentions": sum(services_today_metrics["mentions_by_service"].values()),
                "unique_clients": len(services_today_metrics["all_users"]),
                "by_service": services_discussed_today,
            },
            "time_range": {
                "start_date": (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(),
                "end_date": datetime.datetime.now().isoformat(),
                "days": days,
            },
        }
