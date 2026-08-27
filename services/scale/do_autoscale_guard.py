"""Refuse DigitalOcean droplet mutations against production HA membership."""

from __future__ import annotations

import os

# Pinned production app droplets behind linas-http-lb-lon1. Never autoscale these.
PRODUCTION_DROPLET_IDS = frozenset({510629908, 591901417})
ALLOWED_SCALE_ENVS = frozenset({"staging", "isolated", "omni-cert"})


class DigitalOceanAutoscaleForbidden(PermissionError):
    """Staging-only DO autoscale was asked to touch production or is ungated."""


def assert_droplet_autoscale_allowed(target_droplet_ids: list[int] | None = None) -> None:
    """Fail closed. Creating droplets is not the default scale path on this platform."""
    if (os.getenv("LINAS_AUTOSCALE_DO_STAGING") or "").strip() != "1":
        raise DigitalOceanAutoscaleForbidden("LINAS_AUTOSCALE_DO_STAGING=1 is required")
    if (os.getenv("LINAS_OMNI_CERT_STAGING") or "").strip() != "1":
        raise DigitalOceanAutoscaleForbidden("LINAS_OMNI_CERT_STAGING=1 is required")
    for droplet_id in target_droplet_ids or []:
        if int(droplet_id) in PRODUCTION_DROPLET_IDS:
            raise DigitalOceanAutoscaleForbidden("production_droplet_id_forbidden")
    env = (os.getenv("LINAS_SCALE_ENV") or "").strip().lower()
    if env and env not in ALLOWED_SCALE_ENVS:
        raise DigitalOceanAutoscaleForbidden("scale_env_not_allowed")
    allowed_project = (os.getenv("LINAS_DO_PROJECT_ID_ALLOWED") or "").strip()
    project = (os.getenv("LINAS_DO_PROJECT_ID") or "").strip()
    if allowed_project and project != allowed_project:
        raise DigitalOceanAutoscaleForbidden("project_id_mismatch")
    required_tag = (os.getenv("LINAS_DO_SCALE_TAG") or "").strip()
    present_tag = (os.getenv("LINAS_DO_SCALE_TAG_PRESENT") or "").strip()
    if required_tag and present_tag != required_tag:
        raise DigitalOceanAutoscaleForbidden("scale_tag_mismatch")
    try:
        max_nodes = int(os.getenv("LINAS_SCALE_MAX_NODES") or "0")
        current_nodes = int(os.getenv("LINAS_SCALE_CURRENT_NODES") or "0")
    except ValueError:
        max_nodes, current_nodes = 0, 0
    if max_nodes > 0 and current_nodes >= max_nodes:
        raise DigitalOceanAutoscaleForbidden("max_nodes")


def create_staging_worker_droplet() -> None:
    """No isolated DigitalOcean cluster exists in this repository.

    Production HA is two pinned systemd droplets + a load balancer with exact
    droplet membership. Adding unbounded droplets is the wrong cold-start path
    (minutes to boot) and is forbidden against production IDs.
    """
    assert_droplet_autoscale_allowed()
    raise DigitalOceanAutoscaleForbidden("no_isolated_digitalocean_cluster_in_repo")
