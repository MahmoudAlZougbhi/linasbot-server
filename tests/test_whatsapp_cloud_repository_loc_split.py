"""LOC split: whatsapp cloud repository under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services.whatsapp_cloud.repository import (
    ACTIVE_LIFECYCLES,
    WhatsAppCloudRepository,
    connection_public_view,
    conversation_public_view,
)
from services.whatsapp_cloud.repository_helpers import ACTIVE_LIFECYCLES as HELPER_LIFECYCLES
from services.whatsapp_cloud.repository_helpers import connection_public_view as helper_conn_view
from services.whatsapp_cloud.repository_runtime import WhatsAppCloudRepositoryRuntimeMixin


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_whatsapp_repository_modules_under_500_lines() -> None:
    assert _line_count("services/whatsapp_cloud/repository.py") < 500
    assert _line_count("services/whatsapp_cloud/repository_helpers.py") < 500
    assert _line_count("services/whatsapp_cloud/repository_runtime.py") < 500


def test_whatsapp_repository_preserves_public_api() -> None:
    assert issubclass(WhatsAppCloudRepository, WhatsAppCloudRepositoryRuntimeMixin)
    assert ACTIVE_LIFECYCLES is HELPER_LIFECYCLES
    assert connection_public_view is helper_conn_view
    assert callable(conversation_public_view)
    for name in (
        "create_connection_attempt",
        "get_or_create_conversation",
        "claim_webhook_event",
        "add_audit",
        "grant_pilot",
    ):
        assert callable(getattr(WhatsAppCloudRepository, name))
