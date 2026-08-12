"""LOC split: montymobile_adapter parse mixin under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services.whatsapp_adapters.montymobile_adapter import (
    MontyMobileAdapter,
    _stable_id_when_provider_omits_message_id,
)
from services.whatsapp_adapters.montymobile_adapter_parse import (
    _stable_id_when_provider_omits_message_id as parse_stable_id,
)


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_montymobile_adapter_modules_under_500_lines() -> None:
    assert _line_count("services/whatsapp_adapters/montymobile_adapter.py") < 500
    assert _line_count("services/whatsapp_adapters/montymobile_adapter_parse.py") < 500


def test_montymobile_adapter_preserves_public_api() -> None:
    assert _stable_id_when_provider_omits_message_id is parse_stable_id
    adapter = MontyMobileAdapter(api_token="t", tenant_id="tenant", api_id="aid", source_number="9611")
    assert callable(adapter.send_text_message)
    assert callable(adapter.parse_webhook_message)
    body = {
        "from": {"phone": "+96179999999", "name": "U"},
        "message": {"type": "text", "text": "same"},
    }
    parsed = adapter._parse_montymobile_format(body)
    assert parsed is not None
    assert "synth_" in parsed["message_id"]
