"""LOC split: smart_messaging mixins/helpers under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services.smart_messaging import (
    SmartMessagingService,
    deliver_scheduled_smart_whatsapp,
    message_type_names,
    smart_messaging,
)
from services.smart_messaging_deliver import deliver_scheduled_smart_whatsapp as deliver_fn
from services.smart_messaging_firestore import get_sent_smart_messages_from_firestore


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_smart_messaging_modules_under_500_lines() -> None:
    assert _line_count("services/smart_messaging.py") < 500
    assert _line_count("services/smart_messaging_templates.py") < 500
    assert _line_count("services/smart_messaging_queue.py") < 500
    assert _line_count("services/smart_messaging_appointments.py") < 500
    assert _line_count("services/smart_messaging_deliver.py") < 500
    assert _line_count("services/smart_messaging_firestore.py") < 500


def test_smart_messaging_preserves_public_api() -> None:
    assert deliver_scheduled_smart_whatsapp is deliver_fn
    assert isinstance(smart_messaging, SmartMessagingService)
    assert callable(smart_messaging.schedule_message)
    assert callable(smart_messaging.get_message_content)
    assert callable(smart_messaging.process_scheduled_messages)
    assert callable(smart_messaging.schedule_appointment_reminders)
    assert callable(smart_messaging.clear_daily_messages)
    assert callable(get_sent_smart_messages_from_firestore)
    assert "reminder_24h" in message_type_names
