"""AnalyticsEvents conversation-type metrics helpers (LOC split)."""

from __future__ import annotations

import datetime
import re
from collections import defaultdict
from typing import Any


class AnalyticsEventsConversationMixin:
    """Session rating / masking / conversation 1-2-3 metrics."""

    def _latest_session_rating_by_user(self, events: list[dict[str, Any]]) -> dict[str, int]:
        """Most recent session_rating stars per user_id within the given event list."""
        latest_ts: dict[str, datetime.datetime] = {}
        latest_stars: dict[str, int] = {}
        for event in events:
            if event.get("type") != "session_rating":
                continue
            uid = self._normalize_user_id(event.get("user_id"))
            if not uid:
                continue
            dt = self._parse_timestamp(event.get("timestamp"))
            if not dt:
                continue
            stars = max(1, min(5, self._safe_int(event.get("stars"))))
            prev = latest_ts.get(uid)
            if prev is None or dt >= prev:
                latest_ts[uid] = dt
                latest_stars[uid] = stars
        return latest_stars

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

    def _mask_phone_tail(self, phone: str | None) -> str:
        """Last 4 digits only for display."""
        if not phone:
            return ""
        d = re.sub(r"\D", "", str(phone))
        if len(d) < 4:
            return "****"
        return "***" + d[-4:]

    def _build_conversation_type_metrics(self, events: list[dict[str, Any]]) -> dict[str, Any]:
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
            events_by_user: defaultdict[str, list[tuple[datetime.datetime, dict[str, Any]]]] = defaultdict(list)
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
            sessions: list[dict[str, Any]] = []

            for user_id, user_events in events_by_user.items():
                user_events.sort(key=lambda item: item[0])
                current_session: list[tuple[datetime.datetime, dict[str, Any]]] = []

                for dt, event in user_events:
                    if not current_session:
                        current_session = [(dt, event)]
                        continue

                    previous_dt = current_session[-1][0]
                    inactivity = (dt - previous_dt).total_seconds()

                    if inactivity > session_gap_seconds:
                        sessions.append(
                            {
                                "user_id": user_id,
                                "start": current_session[0][0],
                                "end": current_session[-1][0],
                                "events": [entry[1] for entry in current_session],
                            }
                        )
                        current_session = [(dt, event)]
                    else:
                        current_session.append((dt, event))

                if current_session:
                    sessions.append(
                        {
                            "user_id": user_id,
                            "start": current_session[0][0],
                            "end": current_session[-1][0],
                            "events": [entry[1] for entry in current_session],
                        }
                    )

            definitions = {
                "conversation_1": "General conversation session with no qualification signal and no appointment event.",
                "conversation_2": "Qualified conversation session where intent/profile is captured (service_request or gender), but no appointment event yet.",
                "conversation_3": "Conversion conversation session that includes an appointment event (requested/booked/confirmed/rescheduled/cancelled).",
            }

            stages: dict[str, dict[str, Any]] = {
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

                    stage["examples"].append(
                        {
                            "user_id_masked": self._mask_user_id(session["user_id"]),
                            "session_start": session["start"].isoformat(),
                            "session_end": session["end"].isoformat(),
                            "event_types": sorted(unique_event_types),
                            "event_sequence": preview_sequence,
                            "appointment_statuses": sorted(set(appointment_statuses)),
                            "bot_tokens": session_tokens,
                            "estimated_cost_usd": round(session_cost, 6),
                        }
                    )

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
                stage["estimated_cost_share_pct"] = (
                    round((stage["estimated_cost_usd"] / estimated_total_cost) * 100, 1)
                    if estimated_total_cost > 0
                    else 0
                )
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
