"""WhatsAppFactory is Meta Cloud-only at runtime."""

from __future__ import annotations

import pytest

from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory


@pytest.fixture(autouse=True)
def _reset_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    WhatsAppFactory._current_adapter = None
    WhatsAppFactory._current_provider = "meta"
    monkeypatch.setenv("WHATSAPP_API_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1234567890")
    yield
    WhatsAppFactory._current_adapter = None
    WhatsAppFactory._current_provider = "meta"


def test_factory_defaults_to_meta() -> None:
    adapter = WhatsAppFactory.get_adapter()
    assert WhatsAppFactory.get_current_provider() == "meta"
    assert getattr(adapter, "provider_name", None) == "meta"


def test_factory_refuses_legacy_providers() -> None:
    for name in ("montymobile", "qiscus", "360dialog"):
        with pytest.raises(ValueError, match="unsupported|Meta Cloud|Unknown"):
            WhatsAppFactory.get_adapter(name)
        with pytest.raises(ValueError, match="unsupported|Meta Cloud|Unknown"):
            WhatsAppFactory.switch_provider(name)


def test_factory_accepts_cloud_alias() -> None:
    adapter = WhatsAppFactory.get_adapter("cloud")
    assert WhatsAppFactory.get_current_provider() == "meta"
    assert getattr(adapter, "provider_name", None) == "meta"
