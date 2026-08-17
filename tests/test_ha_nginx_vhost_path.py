"""HA nginx preflight and publish must use the canonical linasaibot vhost."""

from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "ha" / "deploy_meta_release_ha.sh"


def test_preflight_and_publish_use_canonical_linasaibot_vhost() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    preflight = helper[helper.index("node_preflight() {") : helper.index("capture_service_state() {")]
    publish = helper[
        helper.index("publish_nginx_config_atomic() {") : helper.index("install_nginx_maintenance_override() {")
    ]
    assert "/etc/nginx/sites-available/linasaibot" in preflight
    assert "root /opt/linasbot/dashboard/build;" in preflight
    assert "proxy_pass http://127.0.0.1:8003;" in preflight
    assert "/etc/nginx/sites-available/linasbot" not in preflight
    assert "destination=/etc/nginx/sites-available/linasaibot" in publish
    assert "destination=/etc/nginx/sites-available/linasbot" not in publish
    assert helper.count("/etc/nginx/sites-available/linasbot") == 0
