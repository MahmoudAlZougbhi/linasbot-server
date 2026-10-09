# Operations

## SLOs

| Surface | Target |
|---|---|
| API availability | 99.9% |
| API p95, excluding model time | under 300 ms |
| Webhook acknowledgement p99 | under 200 ms |
| AI reply queue wait p95 | under 5 s |

A 99.9% month allows about 43 minutes of downtime. Page when the error budget for the month is half gone.

## On call

One primary and one secondary. Alerts go to the existing monitoring email. Pages: 5xx above 1% for 5 minutes, p95 above 1 second for 10 minutes, oldest queue job above 60 seconds, a new dead letter, Postgres CPU above 80%, Valkey memory above 80%, crash loops, certificate expiry inside 14 days.

## What to do

- Deploy: use `deploy-k8s.yml` for the cluster. The droplet workflow stays until P10.
- Rollback: `kubectl rollout undo deployment/api`. Droplet rollback stays on `deploy.yml` until P10.
- Failover: a database node failure is a DigitalOcean restore. Do not change production DNS during it.
- Restore: `docs/runbooks/restore.md`.
- Queue backlog: check provider 429s before raising worker replicas.
- Provider outage: stop retries from amplifying the outage, serve the last good read, and do not invent replies.
- Secret leak: revoke the key in the provider, then follow `docs/runbooks/secret-rotation.md`.
