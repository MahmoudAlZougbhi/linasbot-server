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
    assert "worker_instances_are_positively_loaded() {" in source
    assert 'test "$load_state" = "loaded"' in source
    for queue in ("high_priority", "interactive", "background", "expensive"):
        assert f"linasbot-worker@{queue}.service" in source
    assert "systemctl cat linasbot-worker@.service" not in source
    assert "worker_instances_maintenance_guard_readback() {" in source
    assert "systemctl show -p DropInPaths --value --" in source
    assert "ConditionPathExists=!/var/lib/linasbot/meta-ha/deploy-node.active" in source
    assert 'systemctl cat -- "linasbot-worker@${queue}.service"' in source
    readback = source[
        source.index("worker_instances_maintenance_guard_readback() {") : source.index("collect_stray_worker_pids() {")
    ]
    assert "DropInPaths" in readback
    assert 'grep -Fq "$worker_guard"' not in readback
    assert "NeedDaemonReload=no is not proof" in source
    stray = source[source.index("collect_stray_worker_pids() {") : source.index("legacy_workerless_eval() {")]
    assert 'entry / "cgroup"' in stray
    assert "linasbot-worker@(?:high_priority|interactive|background|expensive)\\.service" in stray
    install = source[
        source.index("install_maintenance_boot_guard() {") : source.index("assert_maintenance_boot_guard_loaded() {")
    ]
    assert "ensure_worker_template_before_maintenance_guard" in install
    assert "worker_instances_are_positively_loaded" in install
    assert "worker_instances_need_daemon_reload_no" in install
    assert "worker_instances_maintenance_guard_readback" in install
    assert "systemd_unit_need_daemon_reload_is_no linasbot.service" in install
    assert "maintenance_boot_guard_files_match" in install
    assert "maintenance boot guard check failed:" in source
    assert "maintenance boot guard installed and systemd-loaded" in install
    assert "I_UNDERSTAND_SKIPPING_GATES" not in source
    assert "--skip" not in source
    assert "ignore-divergence" not in source
