"""
Persistence layer for message logs and campaign logs.
"""

import json
import os
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from services.smart_messaging_catalog import normalize_template_id
from utils.phone_utils import phone_match_key


class MessageLogsService:
    """Stores deduplication-safe message and campaign logs in JSON files."""

    def __init__(self):
        base_dir = Path(__file__).resolve().parent.parent / "data"
        self.message_logs_file = base_dir / "message_logs.json"
        self.campaign_logs_file = base_dir / "campaign_logs.json"
        self._lock = threading.Lock()

    def _load_list(self, file_path: Path) -> List[Dict[str, Any]]:
        if not file_path.exists():
            return []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []

    def _save_list(self, file_path: Path, records: List[Dict[str, Any]]) -> bool:
        try:
            os.makedirs(file_path.parent, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def _normalize_customer_id(self, customer_id: Optional[Any]) -> str:
        if customer_id is None:
            return ""
        raw = str(customer_id).strip()
        return raw.replace(" ", "").replace("+", "").replace("-", "")

    def was_message_sent(
        self,
        customer_id: Any,
        template_type: str,
        reference_date: Optional[str] = None,
        appointment_id: Optional[Any] = None,
        campaign_id: Optional[str] = None,
    ) -> bool:
        """Check if a matching message has already been logged as sent."""
        normalized_customer = self._normalize_customer_id(customer_id)
        normalized_template = normalize_template_id(template_type)
        normalized_appointment = str(appointment_id) if appointment_id is not None else None

        with self._lock:
            logs = self._load_list(self.message_logs_file)

        for entry in logs:
            if self._normalize_customer_id(entry.get("customer_id")) != normalized_customer:
                continue

            if normalize_template_id(entry.get("template_type")) != normalized_template:
                continue

            if reference_date and str(entry.get("reference_date", "")) != str(reference_date):
                continue

            if normalized_appointment is not None:
                if str(entry.get("appointment_id")) != normalized_appointment:
                    continue

            if campaign_id and str(entry.get("campaign_id", "")) != str(campaign_id):
                continue

            return True

        return False

    def log_message(
        self,
        customer_id: Any,
        template_type: str,
        sent_at: Optional[str] = None,
        appointment_id: Optional[Any] = None,
        campaign_id: Optional[str] = None,
        reference_date: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Append a message log entry."""
        entry = {
            "log_id": f"msg_{uuid.uuid4().hex[:12]}",
            "customer_id": self._normalize_customer_id(customer_id),
            "appointment_id": str(appointment_id) if appointment_id is not None else None,
            "template_type": normalize_template_id(template_type),
            "sent_at": sent_at or datetime.utcnow().isoformat(),
            "reference_date": reference_date,
            "campaign_id": campaign_id,
        }

        if extra:
            entry.update(extra)

        with self._lock:
            logs = self._load_list(self.message_logs_file)
            logs.append(entry)
            self._save_list(self.message_logs_file, logs)

        return entry

    def create_campaign_log(
        self,
        template_type: str,
        filters: Dict[str, Any],
        scheduled_for: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a campaign log entry before execution."""
        campaign_id = f"cmp_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        entry = {
            "campaign_id": campaign_id,
            "template_type": normalize_template_id(template_type),
            "filters": filters,
            "created_at": datetime.utcnow().isoformat(),
            "scheduled_for": scheduled_for,
            "sent_count": 0,
            "preview_count": 0,
            "status": "created",
        }

        with self._lock:
            logs = self._load_list(self.campaign_logs_file)
            logs.append(entry)
            self._save_list(self.campaign_logs_file, logs)

        return entry

    def finalize_campaign_log(
        self,
        campaign_id: str,
        sent_count: int,
        preview_count: int,
        status: str = "completed",
    ) -> Dict[str, Any]:
        """Update campaign log with final stats."""
        updated = None
        with self._lock:
            logs = self._load_list(self.campaign_logs_file)
            for idx, entry in enumerate(logs):
                if entry.get("campaign_id") != campaign_id:
                    continue
                entry = dict(entry)
                entry["sent_count"] = int(sent_count)
                entry["preview_count"] = int(preview_count)
                entry["status"] = status
                entry["updated_at"] = datetime.utcnow().isoformat()
                logs[idx] = entry
                updated = entry
                break
            self._save_list(self.campaign_logs_file, logs)

        if updated is None:
            raise ValueError(f"Campaign '{campaign_id}' not found")

        return updated

    def get_campaign_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            logs = self._load_list(self.campaign_logs_file)
        logs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return logs[:limit]

    def _parse_sent_at_utc(self, raw: Optional[str]) -> Optional[datetime]:
        if not raw or not isinstance(raw, str):
            return None
        try:
            s = raw.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def recipient_phone_keys_for_template(
        self,
        template_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Tuple[Set[str], Dict[str, str], int]:
        """
        Collect distinct recipient phone keys from message_logs for a template,
        optionally limited to sent_at calendar days (UTC) in [date_from, date_to].
        Returns (key_set, latest_sent_at_by_key_iso, matching_log_rows).
        """
        canonical = normalize_template_id(template_id)
        if not canonical:
            return set(), {}, 0

        df: Optional[date] = None
        dt_end: Optional[date] = None
        if date_from:
            try:
                df = date.fromisoformat(str(date_from).strip()[:10])
            except Exception:
                df = None
        if date_to:
            try:
                dt_end = date.fromisoformat(str(date_to).strip()[:10])
            except Exception:
                dt_end = None

        with self._lock:
            logs = self._load_list(self.message_logs_file)

        keys: Set[str] = set()
        latest: Dict[str, str] = {}
        matched = 0

        for entry in logs:
            if normalize_template_id(entry.get("template_type", "")) != canonical:
                continue
            sent = self._parse_sent_at_utc(entry.get("sent_at"))
            if sent:
                d = sent.date()
                if df is not None and d < df:
                    continue
                if dt_end is not None and d > dt_end:
                    continue
            elif df is not None or dt_end is not None:
                # No parseable date — skip when a date filter is active
                continue

            key = phone_match_key(entry.get("customer_id"))
            if not key:
                continue
            matched += 1
            keys.add(key)
            iso = entry.get("sent_at") or ""
            prev = latest.get(key)
            if not prev or (iso and iso > prev):
                latest[key] = iso

        return keys, latest, matched


message_logs_service = MessageLogsService()

