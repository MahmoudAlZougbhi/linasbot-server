"""Inbound buffer jobs must not hold the conversation lock during combine wait."""

from __future__ import annotations

from services.scale.worker_lock_policy import job_requires_conversation_lock


def test_meta_inbound_does_not_hold_conversation_lock() -> None:
    assert job_requires_conversation_lock("meta_inbound_process") is False


def test_generate_and_flush_hold_conversation_lock() -> None:
    assert job_requires_conversation_lock("combine_flush") is True
    assert job_requires_conversation_lock("omni_generate") is True
    assert job_requires_conversation_lock("whatsapp_generate") is True
