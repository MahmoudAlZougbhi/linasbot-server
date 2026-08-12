"""
Smart Messaging API Module
Handles message templates endpoints for the dashboard

Store: smart_messaging_api_store; routes split by domain (LOC split).
"""

from __future__ import annotations

from modules import smart_messaging_api_preview as smart_messaging_api_preview  # noqa: F401
from modules import smart_messaging_api_send_template as smart_messaging_api_send_template  # noqa: F401
from modules import smart_messaging_api_send_test as smart_messaging_api_send_test  # noqa: F401
from modules import smart_messaging_api_settings as smart_messaging_api_settings  # noqa: F401
from modules import smart_messaging_api_status as smart_messaging_api_status  # noqa: F401
from modules import smart_messaging_api_templates as smart_messaging_api_templates  # noqa: F401
from modules.smart_messaging_api_store import (  # noqa: F401
    _TEMPLATE_FILE,
    _TEMPLATE_LOCK_FILE,
    _build_template_record,
    _default_template_ids,
    _load_templates_from_disk,
    _migrate_templates,
    _save_templates_to_disk,
    _template_store_lock,
)
from modules.smart_messaging_api_templates import (  # noqa: F401
    _monty_whatsapp_language_code,
    delete_message_template,
    get_message_templates,
    smart_messaging_resolve_user_language,
    update_message_template,
)
