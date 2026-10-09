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

data "digitalocean_kubernetes_cluster" "staging" {
  name = "linas-staging"
}

data "digitalocean_database_cluster" "postgres" {
  name = "linas-staging-pg"
}

data "digitalocean_database_cluster" "valkey" {
  name = "linas-staging-valkey"
}

output "doks_id" {
  value = data.digitalocean_kubernetes_cluster.staging.id
}

output "postgres" {
  value = data.digitalocean_database_cluster.postgres.name
}

output "valkey" {
  value = data.digitalocean_database_cluster.valkey.name
}
