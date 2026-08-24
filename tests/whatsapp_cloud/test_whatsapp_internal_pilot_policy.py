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


def test_phase1_github_workflow_uses_two_node_ha_transaction() -> None:
    """WhatsApp Phase 1 apply uses the Meta HA env transaction pattern."""

    workflow = (ROOT / ".github/workflows/whatsapp-cloud-phase1-apply.yml").read_text(encoding="utf-8")
    assert "BLOCKED" not in workflow
    assert "two-node" in workflow.lower() or "Two-node" in workflow
    assert "prod_stage_whatsapp_cloud_phase1_flags.sh" in workflow
    assert "scripts/prod_whatsapp_cloud_phase1_ops.sh" in guard.TWO_NODE_ENV_TRANSACTION_REQUIRED
    recovery = workflow.index("--recover-only")
    registration = workflow.index("--register-prestage-backup")
    assert recovery < registration
    assert "clearing_orphan_maintenance_before_apply" not in workflow


def test_require_pilot_defaults_true_while_public_availability_is_off(monkeypatch) -> None:
    """In-process default when PUBLIC is false; not a live production flag proof."""

    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    monkeypatch.delenv("WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT", raising=False)
    from services.whatsapp_cloud.config import get_whatsapp_cloud_flags

    flags = get_whatsapp_cloud_flags()
    assert flags.public_availability is False
    assert flags.require_pilot_entitlement is True
    assert flags.history_sync_enabled is False


def test_phase1_apply_script_sets_only_expected_keys() -> None:
    """Phase 1 flag script must not flip public availability or enable history sync."""

    source = (ROOT / "scripts/prod_apply_whatsapp_cloud_phase1_flags.sh").read_text(encoding="utf-8")
    assert '"WHATSAPP_CLOUD_PUBLIC_AVAILABILITY": "false"' in source
    assert '"WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED": "false"' in source
    assert '"WHATSAPP_CLOUD_CONNECTION_UI_ENABLED": "true"' in source
    assert '"WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED": "true"' in source
    assert '"WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED": "true"' in source
    assert '"WHATSAPP_CLOUD_AI_REPLIES_ENABLED": "true"' in source
    assert '"WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT": "true"' in source
    assert "from scripts.ha.production_env_cas import atomic_update_canonical_env" in source
    assert "systemctl restart linasbot" in source


def test_phase1_ops_script_rejects_unknown_mode() -> None:
    source = (ROOT / "scripts/prod_whatsapp_cloud_phase1_ops.sh").read_text(encoding="utf-8")
    assert 'echo "[wa-ops] BLOCKED: unknown mode=${MODE}"' in source
    assert "exit 2" in source
    assert "APPLY_WHATSAPP_CLOUD_PHASE1_FLAGS_ONLY" in source
    assert "APPLY_WHATSAPP_CLOUD_PHASE1" in source


def test_stage_script_requires_ha_transaction() -> None:
    source = (ROOT / "scripts/prod_stage_whatsapp_cloud_phase1_flags.sh").read_text(encoding="utf-8")
    assert 'META_HA_STAGE_ONLY:-}" != "true"' in source
    assert "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY" in source
    assert "atomic_update_env" in source
    assert "systemctl restart" not in source
