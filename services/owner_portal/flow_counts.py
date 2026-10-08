"""Channel counts for the owner overview, without the 500-row activity buffer."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import text


def accumulate_channel_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    channels: Counter[str] = Counter()
    types: Counter[str] = Counter()
    for row in rows:
        channels[str(row.get("channel") or "unknown")] += 1
        types[str(row.get("message_type") or "text")] += 1
    return {"messages_by_channel": dict(channels), "comments": int(types.get("comment", 0))}


def _in_range(value: Any, start: datetime, end: datetime) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=start.tzinfo)
    return start <= parsed < end


def _file_rows(start: datetime, end: datetime) -> list[dict[str, Any]]:
    from services.owner_copilot.interaction_flow_logger import _FLOW_BUFFER, FLOW_LOG_FILE

    rows: list[dict[str, Any]] = []
    if os.path.isfile(FLOW_LOG_FILE):
        with open(FLOW_LOG_FILE, encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict) and _in_range(item.get("timestamp"), start, end):
                    rows.append(item)
        return rows
    for item in _FLOW_BUFFER:
        if isinstance(item, dict) and _in_range(item.get("timestamp"), start, end):
            rows.append(item)
    return rows


def sql_channel_counts(start: datetime, end: datetime) -> dict[str, int] | None:
    from db.session import whatsapp_session

    try:
        with whatsapp_session(require=False) as session:
            if session is None:
                return None
            found = session.execute(
                text(
                    """
                    SELECT channel, count(*)
                    FROM omnichannel_inbound_events
                    WHERE created_at >= :start AND created_at < :end
                      AND channel <> 'brains_test'
                    GROUP BY channel
                    """
                ),
                {"start": start, "end": end},
            ).all()
    except Exception:
        return None
    return {str(row[0] or "unknown"): int(row[1]) for row in found}


def channel_counts_for_range(start: datetime, end: datetime) -> dict[str, Any]:
    """SQL aggregate only. Lab turns are not customer traffic, and the jsonl is not scanned."""
    sql_counts = sql_channel_counts(start, end) or {}
    return {"messages_by_channel": sql_counts, "comments": int(sql_counts.get("comment", 0))}
