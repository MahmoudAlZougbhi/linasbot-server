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


def test_cloud_blocks_monty_send_true_when_scan_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONTYMOBILE_SOURCE_NUMBER", "96170123456")
    monkeypatch.setattr(
        li,
        "cloud_bound_display_digits",
        lambda: (_ for _ in ()).throw(li.LegacyIsolationScanError("scan failed")),
    )
    assert li.cloud_blocks_monty_send("96170123456") is True


def test_cloud_blocks_monty_send_false_for_unrelated_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONTYMOBILE_SOURCE_NUMBER", "96170123456")
    # Scan must not even run for non-source destinations; if it did and failed, we'd still
    # only block when digits == monty source.
    monkeypatch.setattr(
        li,
        "cloud_bound_display_digits",
        lambda: (_ for _ in ()).throw(li.LegacyIsolationScanError("should not be called")),
    )
    assert li.cloud_blocks_monty_send("96170999999") is False


def test_assert_no_monty_cloud_dual_bind_raises_on_scan_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONTYMOBILE_SOURCE_NUMBER", "96170123456")
    monkeypatch.setattr(
        li,
        "cloud_bound_display_digits",
        lambda: (_ for _ in ()).throw(li.LegacyIsolationScanError("scan failed")),
    )
    monkeypatch.setattr(li, "emit_wa_event", lambda *a, **k: None)

    with pytest.raises(RuntimeError, match="cannot verify Monty/Cloud isolation"):
        li.assert_no_monty_cloud_dual_bind()


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
