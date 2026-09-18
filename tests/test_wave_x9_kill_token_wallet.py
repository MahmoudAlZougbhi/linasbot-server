"""WAVE X9: token_wallet dual gone; credit ledger is the live meter; Owner Catalog stays."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wave_x9_token_wallet_modules_gone() -> None:
    leftover = list((ROOT / "services" / "billing").glob("token_wallet_*.py"))
    assert leftover == []
    for rel in (
        "services/billing/membership/message_catalog.py",
        "modules/platform_message_api.py",
        "dashboard/src/owner_portal/pages/OwnerCatalog.jsx",
        "services/billing/credit_ai_gate.py",
        "services/billing/credit_ledger_service.py",
        "services/billing/iap_product_catalog.py",
    ):
        assert (ROOT / rel).is_file(), rel
    iap = (ROOT / "services/billing/iap_product_catalog.py").read_text(encoding="utf-8")
    assert "com.linasai.credits." in iap


def test_wave_x9_no_runtime_token_wallet_imports() -> None:
    hits: list[str] = []
    for folder in ("services", "modules"):
        for path in (ROOT / folder).rglob("*.py"):
            if "token_wallet" in path.read_text(encoding="utf-8"):
                hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_wave_x9_copilot_and_stripe_use_credits() -> None:
    account = (ROOT / "services/owner_copilot/account_state.py").read_text(encoding="utf-8")
    tools = (ROOT / "services/owner_copilot/tools_read.py").read_text(encoding="utf-8")
    webhook = (ROOT / "modules/wallet_api.py").read_text(encoding="utf-8")
    keep = (ROOT / "docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    assert "token_wallet_service" not in account
    assert "token_wallet_service" not in tools
    assert "owner_credits_public" in account
    assert "owner_credits_public" in tools
    assert "token_pack_retired" in webhook
    assert "token_wallet_service" not in webhook
    assert "WAVE X9" in keep
