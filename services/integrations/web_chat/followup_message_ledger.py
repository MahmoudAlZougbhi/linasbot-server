"""Website Chat operation FSM uses a short message-ledger reservation id.

Live turns and follow-up reserve/settle message units. The stored
reservation_id is hashed so it fits web_chat_operations.reservation_id.
"""

from __future__ import annotations

import hashlib

MESSAGE_RESERVATION_PREFIX = "msg:"
_RESERVATION_DIGEST_LEN = 28


def followup_uses_message_ledger() -> bool:
    return True


def is_message_reservation(reservation_id: str | None) -> bool:
    return str(reservation_id or "").startswith(MESSAGE_RESERVATION_PREFIX)


def message_reservation_id(request_id: str) -> str:
    digest = hashlib.sha256(str(request_id or "").encode("utf-8")).hexdigest()[:_RESERVATION_DIGEST_LEN]
    return f"{MESSAGE_RESERVATION_PREFIX}{digest}"


def credit_reservation_required(reservation_id: str | None) -> bool:
    _ = reservation_id
    return False
