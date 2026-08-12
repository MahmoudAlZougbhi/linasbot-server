"""Light intent helpers for Requests capture (order / appointment preference)."""

from __future__ import annotations

import re

_ORDER_RE = re.compile(
    r"\b(order|buy|purchase|طلب|اطلب|بدي\s*اطلب|bade\s*otlob|commande)\b",
    re.I,
)
_APPOINTMENT_RE = re.compile(
    r"\b(book|appointment|reserve|حجز|احجز|موعد|a7jez|7jez|rendez-?vous)\b",
    re.I,
)


def is_order_intent(message: str | None) -> bool:
    return bool(_ORDER_RE.search(message or ""))


def looks_like_order_intent(message: str | None) -> bool:
    return is_order_intent(message)


def looks_like_appointment_intent(message: str | None) -> bool:
    return bool(_APPOINTMENT_RE.search(message or ""))


def is_appointment_or_order_intent(message: str | None) -> bool:
    text = message or ""
    if is_order_intent(text):
        return True
    return looks_like_appointment_intent(text)
