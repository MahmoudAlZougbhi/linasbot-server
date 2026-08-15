"""Exact DigitalOcean LB ready projection contract (Phase 1B DUALSTACK)."""

from __future__ import annotations

from typing import Any

LB_NAME = "linas-http-lb-lon1"
LB_PROJECT_ID = "70160077-6e21-4fc7-9c81-45e6b60d8919"
LB_DROPLETS = [510629908, 591901417]
LB_SUBNET_UUID = "2415d1ce-b8e6-4707-bc89-56e234548d60"
LB_VPC_UUID = "d0e11d67-3fba-4966-b2db-6a471307df85"
LB_NETWORK_STACK = "DUALSTACK"
LB_SIZE_UNIT = 1
OLD_HEALTH_PATH = "/api/health"
READY_HEALTH_PATH = "/api/ready"

LB_READY_PROJECTION_KEYS = frozenset(
    {
        "disable_lets_encrypt_dns_records",
        "droplet_ids",
        "enable_backend_keepalive",
        "enable_proxy_protocol",
        "forwarding_rules",
        "health_check",
        "http_idle_timeout_seconds",
        "name",
        "network_stack",
        "project_id",
        "redirect_http_to_https",
        "region",
        "size_unit",
        "sticky_sessions",
        "subnet_uuid",
        "type",
        "vpc_uuid",
    }
)

LB_HEALTH_CONTRACT = {
    "protocol": "http",
    "port": 8003,
    "check_interval_seconds": 5,
    "response_timeout_seconds": 3,
    "healthy_threshold": 2,
    "unhealthy_threshold": 3,
}

LB_HEALTH_CONTRACT_READY = {**LB_HEALTH_CONTRACT, "path": READY_HEALTH_PATH}
LB_HEALTH_CONTRACT_OLD = {**LB_HEALTH_CONTRACT, "path": OLD_HEALTH_PATH}


def validate_observed_get_routing(load_balancer: dict[str, Any]) -> None:
    if "network" in load_balancer:
        raise RuntimeError("DigitalOcean load-balancer network field is forbidden in observed GET")
    size_unit = load_balancer.get("size_unit")
    if size_unit != LB_SIZE_UNIT:
        raise RuntimeError("DigitalOcean load-balancer routing/safety contract changed")
    if (
        load_balancer.get("redirect_http_to_https") is not True
        or load_balancer.get("enable_backend_keepalive") is not True
        or load_balancer.get("disable_lets_encrypt_dns_records") is not False
        or load_balancer.get("enable_proxy_protocol") is not False
        or not 30 <= int(load_balancer.get("http_idle_timeout_seconds") or 0) <= 600
        or load_balancer.get("network_stack") != LB_NETWORK_STACK
        or load_balancer.get("type") != "REGIONAL"
        or load_balancer.get("subnet_uuid") != LB_SUBNET_UUID
        or load_balancer.get("vpc_uuid") != LB_VPC_UUID
        or load_balancer.get("sticky_sessions") != {"type": "none"}
    ):
        raise RuntimeError("DigitalOcean load-balancer routing/safety contract changed")


def validate_ready_projection_keyset(projection: dict[str, Any]) -> None:
    if "network" in projection:
        raise RuntimeError("DigitalOcean ready projection contains forbidden network key")
    if set(projection) != LB_READY_PROJECTION_KEYS:
        raise RuntimeError("DigitalOcean ready projection has an incomplete or unknown keyset")


def validate_ready_projection_values(projection: dict[str, Any]) -> None:
    validate_ready_projection_keyset(projection)
    if (
        projection.get("name") != LB_NAME
        or projection.get("region") != "lon1"
        or projection.get("project_id") != LB_PROJECT_ID
        or projection.get("network_stack") != LB_NETWORK_STACK
        or projection.get("type") != "REGIONAL"
        or projection.get("size_unit") != LB_SIZE_UNIT
        or projection.get("enable_proxy_protocol") is not False
        or projection.get("subnet_uuid") != LB_SUBNET_UUID
        or projection.get("vpc_uuid") != LB_VPC_UUID
        or projection.get("sticky_sessions") != {"type": "none"}
        or projection.get("redirect_http_to_https") is not True
        or projection.get("enable_backend_keepalive") is not True
        or projection.get("disable_lets_encrypt_dns_records") is not False
    ):
        raise RuntimeError("DigitalOcean ready projection routing identity changed")
    idle = projection.get("http_idle_timeout_seconds")
    if isinstance(idle, bool) or not isinstance(idle, int) or not 30 <= idle <= 600:
        raise RuntimeError("DigitalOcean ready projection idle timeout is invalid")
    try:
        droplet_ids = sorted(int(value) for value in projection.get("droplet_ids") or [])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("DigitalOcean ready projection backend membership is invalid") from exc
    if droplet_ids != sorted(LB_DROPLETS):
        raise RuntimeError("DigitalOcean ready projection backend membership changed")
    if projection.get("health_check") != LB_HEALTH_CONTRACT_READY:
        raise RuntimeError("DigitalOcean ready projection does not prove direct :8003 /api/ready")
    forwarding = projection.get("forwarding_rules")
    if (
        not isinstance(forwarding, list)
        or len(forwarding) != 2
        or any(not isinstance(rule, dict) for rule in forwarding)
    ):
        raise RuntimeError("DigitalOcean ready projection forwarding rules are invalid")
    normalized = {
        (
            rule.get("entry_protocol"),
            rule.get("entry_port"),
            rule.get("target_protocol"),
            rule.get("target_port"),
        )
        for rule in forwarding
    }
    if normalized != {("http", 80, "http", 80), ("https", 443, "http", 80)}:
        raise RuntimeError("DigitalOcean ready projection forwarding rules changed")
    https_rule = next(rule for rule in forwarding if rule.get("entry_protocol") == "https")
    if not isinstance(https_rule.get("certificate_id"), str) or not https_rule["certificate_id"]:
        raise RuntimeError("DigitalOcean ready projection HTTPS certificate is missing")
