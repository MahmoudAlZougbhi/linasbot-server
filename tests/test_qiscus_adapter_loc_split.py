"""LOC split: qiscus_adapter parse mixin under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.whatsapp_adapters.qiscus_adapter import QiscusAdapter
from services.whatsapp_adapters.qiscus_adapter_parse import QiscusAdapterParseMixin
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_qiscus_adapter_modules_under_500_lines() -> None:
    assert _line_count("services/whatsapp_adapters/qiscus_adapter.py") < 500
    assert _line_count("services/whatsapp_adapters/qiscus_adapter_parse.py") < 500


def test_qiscus_adapter_preserves_public_api() -> None:
    adapter = QiscusAdapter(api_token="t", app_code="app", sender_email="a@b.c")
    assert isinstance(adapter, QiscusAdapterParseMixin)
    assert callable(adapter.send_text_message)
    assert callable(adapter.parse_webhook_message)
    assert callable(adapter.get_room_id_for_user)
    # Archived: factory keeps create method but refuses runtime selection
    assert WhatsAppFactory._create_qiscus_adapter.__name__ == "_create_qiscus_adapter"
    with pytest.raises(ValueError, match="unsupported|Meta Cloud"):
        WhatsAppFactory._create_qiscus_adapter()
    src = Path("services/whatsapp_adapters/whatsapp_factory.py").read_text(encoding="utf-8")
    assert "QiscusAdapter" not in src or "unsupported" in src
    assert ' _current_provider: str = "meta"' in src or '_current_provider: str = "meta"' in src
