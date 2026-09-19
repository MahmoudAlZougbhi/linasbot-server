"""Website Chat operation FSM uses a message-ledger sentinel reservation.

Live turns and follow-up do not charge leftover credits. Follow-up still
settles the message unit after send.
"""

from __future__ import annotations

MESSAGE_RESERVATION_PREFIX = "msg:"


def followup_uses_message_ledger() -> bool:
    return True


def is_message_reservation(reservation_id: str | None) -> bool:
    return str(reservation_id or "").startswith(MESSAGE_RESERVATION_PREFIX)


def message_reservation_id(request_id: str) -> str:
    return f"{MESSAGE_RESERVATION_PREFIX}{request_id}"


def credit_reservation_required(reservation_id: str | None) -> bool:
    _ = reservation_id
    return False
