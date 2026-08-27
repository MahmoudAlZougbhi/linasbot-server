"""Refuse DigitalOcean droplet mutations against production HA membership."""

from __future__ import annotations

import os

# Pinned production app droplets behind linas-http-lb-lon1. Never autoscale these.
PRODUCTION_DROPLET_IDS = frozenset({510629908, 591901417})


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


def create_staging_worker_droplet() -> None:
    """No isolated DigitalOcean cluster exists in this repository.

    Production HA is two pinned systemd droplets + a load balancer with exact
    droplet membership. Adding unbounded droplets is the wrong cold-start path
    (minutes to boot) and is forbidden against production IDs.
    """
    assert_droplet_autoscale_allowed()
    raise DigitalOceanAutoscaleForbidden("no_isolated_digitalocean_cluster_in_repo")
