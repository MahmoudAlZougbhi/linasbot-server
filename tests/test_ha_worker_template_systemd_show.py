"""Worker template load checks must query concrete systemd instance names."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def test_worker_need_daemon_reload_queries_instances_not_the_template() -> None:
    source = HELPER.read_text(encoding="utf-8")
    assert "systemctl show -p NeedDaemonReload --value linasbot-worker@.service" not in source
    assert "worker_instances_need_daemon_reload_no() {" in source
    assert "systemd_unit_need_daemon_reload_is_no() {" in source
    assert 'systemd_unit_need_daemon_reload_is_no "linasbot-worker@${queue}.service"' in source
    for queue in ("high_priority", "interactive", "background", "expensive"):
        assert f"linasbot-worker@{queue}.service" in source
    assert "systemctl cat linasbot-worker@.service" not in source
    assert "worker_instances_maintenance_guard_readback() {" in source
    assert 'systemctl cat -- "linasbot-worker@${queue}.service"' in source
    install = source[
        source.index("install_maintenance_boot_guard() {") : source.index("assert_maintenance_boot_guard_loaded() {")
    ]
    assert "worker_instances_need_daemon_reload_no" in install
    assert "worker_instances_maintenance_guard_readback" in install
    assert "systemd_unit_need_daemon_reload_is_no linasbot.service" in install
    assert "I_UNDERSTAND_SKIPPING_GATES" not in source
    assert "--skip" not in source
    assert "ignore-divergence" not in source
