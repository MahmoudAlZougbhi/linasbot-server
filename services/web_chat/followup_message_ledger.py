"""Website Chat billing when the message ledger is the SoT.

Credit reservations stay required until MESSAGE_BILLING_ENABLED. After that,
live turns and follow-up use a sentinel reservation so the operation FSM can
advance without charging leftover credits. Follow-up still settles the message
unit after send.
"""

from __future__ import annotations

MESSAGE_RESERVATION_PREFIX = "msg:"


def followup_uses_message_ledger() -> bool:
    from services.membership.message_flags import message_billing_enabled

    return message_billing_enabled()


def is_message_reservation(reservation_id: str | None) -> bool:
    return str(reservation_id or "").startswith(MESSAGE_RESERVATION_PREFIX)


def message_reservation_id(request_id: str) -> str:
    return f"{MESSAGE_RESERVATION_PREFIX}{request_id}"


def credit_reservation_required(reservation_id: str | None) -> bool:
    return not followup_uses_message_ledger() and not str(reservation_id or "").strip()
