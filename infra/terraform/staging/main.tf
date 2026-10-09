resource "digitalocean_vpc" "staging" {
  name   = "linas-staging"
  region = var.region
}

resource "digitalocean_kubernetes_cluster" "staging" {
  name     = "linas-staging"
  region   = var.region
  version  = var.kubernetes_version
  vpc_uuid = digitalocean_vpc.staging.id

  node_pool {
    name       = "app"
    size       = "s-2vcpu-4gb"
    node_count = 2
    auto_scale = true
    min_nodes  = 2
    max_nodes  = 4
  }
}

resource "digitalocean_database_cluster" "postgres" {
  name                 = "linas-staging-pg"
  engine               = "pg"
  version              = "16"
  size                 = "db-amd-1vcpu-2gb"
  region               = var.region
  node_count           = 1
  private_network_uuid = digitalocean_vpc.staging.id
}

resource "digitalocean_database_connection_pool" "app" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = "app"
  mode       = "transaction"
  size       = 10
  db_name    = "defaultdb"
  user       = "doadmin"
}

resource "digitalocean_database_cluster" "valkey" {
  name                 = "linas-staging-valkey"
  engine               = "valkey"
  version              = "8"
  size                 = "db-amd-1vcpu-1gb"
  region               = var.region
  node_count           = 1
  private_network_uuid = digitalocean_vpc.staging.id
}

resource "digitalocean_spaces_bucket" "media" {
  count  = var.spaces_access_key_id == "" ? 0 : 1
  name   = "linas-staging-media"
  region = var.region
  acl    = "private"
}
