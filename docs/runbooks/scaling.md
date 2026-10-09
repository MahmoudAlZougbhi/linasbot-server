# Scaling

Start small. 100k users is the design target, not the size to buy now.

A single-node managed Postgres has no automatic failover. If that node fails, DigitalOcean replaces it and the app is down for minutes, while PITR covers the data. A standby fails over in under a minute and doubles the database cost. Production already has `linas-postgres-prod` (two nodes). Do not add another standby until a trigger below says so. Valkey holds nothing authoritative: a restart costs the cache and a realtime reconnect.

## Start

| Component | Start | Cap |
|---|---|---|
| DOKS | 1 pool, 2 × s-2vcpu-4gb, free control plane | autoscaler min 2 / max 4 |
| api | 2 replicas, 250m CPU / 384Mi | HPA max 6 |
| worker-interactive | 1 | KEDA max 6 |
| worker-background | 1 | KEDA max 3 |
| scheduler | 1 | fixed |
| ingress-nginx | 2 | fixed |
| Postgres | existing `linas-postgres-prod`, PgBouncer transaction pool | upsize, do not replace |
| Valkey | existing `linas-redis-prod`, 1 GB class | upsize |
| Edge | Cloudflare Free. DNS for the droplets stays until P10 | Pro when more WAF rules are needed |

Estimated infra cost now is about $110–190 a month, excluding model APIs. About 1k users is $300–450. About 10k is $800–1,300. About 100k is $1,200–2,100 baseline and $3,100–5,000 at peak.

## When to grow

- Pods stay Pending for 5 minutes, or the pool sits at max for 30 minutes: raise the cluster max. Move to s-4vcpu-8gb when one pod needs more than 1.5 vCPU or 2 GiB.
- API HPA stays at max for 30 minutes, or p95 stays above 400 ms for 15 minutes at max: raise the replica max.
- Oldest job stays above 30 seconds for 10 minutes at max replicas: check provider 429s before raising the worker max.
- Postgres, for 3 peak-hour days: CPU above 70%, cache hit below 99%, connections above 70% of the pool, storage above 70%, or top-query p95 above 50 ms. Size path: 2 GB, 4 GB, 8 GB, 16 GB, 32 GB. Upsize at low traffic.
- Add a Postgres standby at the first of: more than 100 paying tenants, an SLA, the first unplanned database outage, or about 1k users.
- Add a read replica when dashboard reads are about 40% of primary CPU, or at about 10k users.
- Valkey memory above 70% or any evictions: next size. HA Valkey at about 1k users.
- DOKS HA control plane at about 1k paying users.
- Split web, worker, and system pools at about 10k users.
- Cloudflare Pro when custom WAF rules are required.

## Deploys

`deploy.yml` and `scripts/ha/*` still run the droplets. They are deprecated for new releases. The replacement is `.github/workflows/deploy-k8s.yml`: expand-only migration, rolling update with `maxUnavailable: 0`, then rollback with `kubectl rollout undo`. It does not move DNS. F-002 happened because the droplet deploy drained both nodes before traffic returned.

## Edge, prepared and not switched

P10 will proxy `linasaibot.com` and `portal.linasaibot.com` through Cloudflare with TLS full-strict, the managed WAF ruleset, and rate limits on `/api/auth/*`, `/api/web-chat/*`, and the webhook paths. Those records are not changed in P05.
