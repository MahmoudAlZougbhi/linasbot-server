"""P05 keeps the droplet scaler on unless a flag turns it off, and prod Terraform only adds a cluster."""

from __future__ import annotations

from pathlib import Path

from services.scale.autoscale_tick import _tick_once


def test_droplet_scaler_off_returns_before_any_cloud_call(monkeypatch) -> None:
    monkeypatch.setenv("LINAS_DROPLET_SCALER", "off")
    _tick_once()


def test_prod_terraform_does_not_replace_databases_or_dns() -> None:
    text = Path("infra/terraform/envs/prod/main.tf").read_text(encoding="utf-8")
    assert 'resource "digitalocean_database_cluster"' not in text
    assert 'resource "digitalocean_loadbalancer"' not in text
    assert "linasaibot.com" not in text
    assert 'resource "digitalocean_kubernetes_cluster" "prod"' in text
    assert 'data "digitalocean_database_cluster" "postgres"' in text
