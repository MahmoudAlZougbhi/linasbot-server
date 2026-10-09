terraform {
  required_version = ">= 1.6.0"
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
  }
}

provider "digitalocean" {}

data "digitalocean_database_cluster" "postgres" {
  name = "linas-postgres-prod"
}

data "digitalocean_database_cluster" "valkey" {
  name = "linas-redis-prod"
}

resource "digitalocean_vpc" "doks" {
  name   = "linas-prod-doks"
  region = "lon1"
}

resource "digitalocean_kubernetes_cluster" "prod" {
  name     = "linas-prod-doks"
  region   = "lon1"
  version  = "1.34.12-do.0"
  vpc_uuid = digitalocean_vpc.doks.id

  node_pool {
    name       = "app"
    size       = "s-2vcpu-4gb"
    node_count = 2
    auto_scale = true
    min_nodes  = 2
    max_nodes  = 4
  }
}

output "reused_postgres" {
  value = data.digitalocean_database_cluster.postgres.name
}

output "reused_valkey" {
  value = data.digitalocean_database_cluster.valkey.name
}

output "doks_id" {
  value = digitalocean_kubernetes_cluster.prod.id
}
