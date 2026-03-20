# -*- coding: utf-8 -*-
"""Strict booking intent → validation → CRM execution pipeline."""

from services.booking.intent_pipeline import handle_submit_booking_intent
from services.booking.schemas import empty_booking_intent_template, validation_error_response

__all__ = [
    "handle_submit_booking_intent",
    "empty_booking_intent_template",
    "validation_error_response",
]
