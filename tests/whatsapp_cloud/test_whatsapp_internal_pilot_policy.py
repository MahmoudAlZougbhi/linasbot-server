"""Repo/default WhatsApp policy contracts only.

These tests read committed scripts, the blocked GHA, and in-process flag defaults.
They do not prove live production flags, a pilot entitlement row, WABA/phone/config
IDs, webhook callback wiring, or end-to-end WhatsApp chat.
"""

from __future__ import annotations

from pathlib import Path

from scripts.ha import production_mutation_guard as guard

ROOT = Path(__file__).resolve().parents[2]


def test_phase1_flags_script_keeps_public_off_and_does_not_enable_history() -> None:
    """Committed apply script contract only; not a live production env read."""

    source = (ROOT / "scripts/prod_apply_whatsapp_cloud_phase1_flags.sh").read_text(encoding="utf-8")
    assert '"WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "false"' in source
    assert '"WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT": "true"' in source
    assert '"WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED": "false"' in source
    assert '"WHATSAPP_CLOUD_CONNECTION_UI_ENABLED": "true"' in source
    assert '"WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED": "true"' in source
    assert '"WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED": "true"' in source
    assert '"WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "true"' not in source


def test_phase1_github_workflow_stays_blocked_for_single_node_env() -> None:
    """Repo HA guard contract only; does not apply or inspect production flags."""

    workflow = (ROOT / ".github/workflows/whatsapp-cloud-phase1-apply.yml").read_text(encoding="utf-8")
    assert "BLOCKED" in workflow
    assert "two-node" in workflow
    assert "exit 1" in workflow
    assert "scripts/prod_whatsapp_cloud_phase1_ops.sh" in guard.TWO_NODE_ENV_TRANSACTION_REQUIRED


def test_require_pilot_defaults_true_while_public_availability_is_off(monkeypatch) -> None:
    """In-process default when PUBLIC is false; not a live production flag proof."""

    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    monkeypatch.delenv("WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT", raising=False)
    from services.whatsapp_cloud.config import get_whatsapp_cloud_flags

    flags = get_whatsapp_cloud_flags()
    assert flags.public_availability is False
    assert flags.require_pilot_entitlement is True
    assert flags.history_sync_enabled is False
