# Incident: database VPC move caused 503s

Date: 2026-10-10. Times below are Cairo (UTC+3).

## What happened

The managed Postgres and Valkey clusters were moved from VPC `default-lon1` (`d0e11d67-3fba-4966-b2db-6a471307df85`, `10.106.0.0/20`) into VPC `linas-prod-doks` (`d4b4341f-3cab-4e78-b8cd-cf1195dc9a43`, `10.106.64.0/20`).

The droplets were still in `default-lon1` and their env files used the private database hostnames. After the move those names resolved to `10.106.64.6`, which is not routed from the droplet VPC. The app processes stopped answering. The load balancer at `157.245.31.104` returned 503 ("No server is available") for several minutes. https://linasaibot.com/api/health and `/api/ready` both failed.

## Recovery

Droplet trusted sources were put back on both databases. On both droplets, `LINAS_WHATSAPP_DATABASE_URL`, `REDIS_URL`, and `RATE_LIMIT_REDIS_URL` were pointed at the public hostnames (the `private-` prefix removed). `linasbot` was restarted. A direct `select 1` on node01 succeeded. The load balancer returned health 200 and ready 200.

Customer traffic stayed on the droplets. The cluster was not given any public weight.

## Cause

A database network move was applied while the only app servers still in service depended on the old private addresses. There was no test connection from a droplet, and no 2-second health poll with an immediate rollback.

## Guard

`scripts/ops/db_network_guard.sh` must pass before any later database or VPC change:

1. Poll https://linasaibot.com/api/health every 2 seconds and require zero non-200.
2. From a droplet, open a test connection to the candidate host without editing `.env`.
3. Switch one droplet only after that test returns success.
4. If any health poll is non-200, put the previous host back and restart that droplet before touching the other.

VPC peering `linas-droplets-to-doks` (`f4cc78ef-c83d-4e6a-96f3-b797be790258`) is active between `default-lon1` and `linas-prod-doks`. A TCP check from node01 to `10.106.64.6:25060` still failed after the peering became active, so the droplet env was not switched back to the private host.
