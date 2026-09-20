"""S1: Meta registry off must not silently bind tenant_id=linas."""

from __future__ import annotations

from pathlib import Path

from services.integrations.meta.meta_legacy_tenant import (
    legacy_webhook_tenant_id,
    meta_legacy_single_tenant_opt_in,
)


def test_legacy_tenant_empty_without_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("LINAS_META_LEGACY_SINGLE_TENANT", raising=False)
    monkeypatch.delenv("LINAS_META_REQUIRE_REGISTRY", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("LINASBOT_TENANT_ID", "linas")
    assert meta_legacy_single_tenant_opt_in() is False
    assert legacy_webhook_tenant_id() == ""


def test_legacy_opt_in_uses_env_tenant_not_hardcoded(monkeypatch) -> None:
    monkeypatch.setenv("LINAS_META_LEGACY_SINGLE_TENANT", "1")
    monkeypatch.delenv("LINAS_META_REQUIRE_REGISTRY", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("LINASBOT_TENANT_ID", "shop-a")
    assert legacy_webhook_tenant_id() == "shop-a"


def test_webhook_module_has_no_silent_linas_bind() -> None:
    src = Path("modules/meta_messaging_webhook.py").read_text(encoding="utf-8")
    assert 'tenant_id="linas"' not in src
    assert "tenant_id='linas'" not in src
