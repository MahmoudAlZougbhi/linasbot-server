"""legacy_isolation: Cloud bind scan must fail closed (never empty-set on DB error)."""

from __future__ import annotations

import pytest

from services.whatsapp_cloud import legacy_isolation as li


def test_cloud_bound_display_digits_raises_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(li, "whatsapp_db_configured", lambda: True)

    def _boom() -> None:
        raise RuntimeError("db_down")

    monkeypatch.setattr(li, "whatsapp_session", _boom)
    monkeypatch.setattr(li, "emit_wa_event", lambda *a, **k: None)

    with pytest.raises(li.LegacyIsolationScanError):
        li.cloud_bound_display_digits()


def test_cloud_bound_display_digits_empty_when_db_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(li, "whatsapp_db_configured", lambda: False)
    assert li.cloud_bound_display_digits() == set()


def test_is_phone_number_id_cloud_bound_raises_on_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(li, "whatsapp_db_configured", lambda: True)

    class _BadSession:
        def __enter__(self):
            raise RuntimeError("db_down")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(li, "whatsapp_session", lambda: _BadSession())
    monkeypatch.setattr(li, "emit_wa_event", lambda *a, **k: None)

    with pytest.raises(li.LegacyIsolationScanError):
        li.is_phone_number_id_cloud_bound("12345")
