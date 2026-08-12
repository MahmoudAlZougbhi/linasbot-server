# Database Capacity Plan — Linas AI

**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**Scope:** WhatsApp/Requests PostgreSQL via `db/session.py` (+ Firestore separately).

## Current pool defaults (DECLARED)

| Setting | Default | Env |
|---------|---------|-----|
| `pool_size` | 5 | `LINAS_WHATSAPP_DB_POOL_SIZE` |
| `max_overflow` | 10 | `LINAS_WHATSAPP_DB_MAX_OVERFLOW` |
| Max connections **per process** | **15** | pool_size + max_overflow |

No PgBouncer observed in Linas topology today.

## Connection budget formula

```
max_db_connections_used ≈
  (API_replicas × API_workers_per_replica × 15)
  + (AI_workers × 15)
  + (outbound_workers × 15)
  + (request_workers × 15)
  + admin/migrate headroom (5–10)
```

Assume managed Postgres default max_connections ≈ 25–100 depending on size (UNKNOWN for current Linas PG host — confirm before raising replicas).

## Safe replica guidance (planning)

| Topology | API procs | Worker procs | Est. peak PG conns | Notes |
|----------|-----------|--------------|--------------------|-------|
| Current single droplet | 1 | 0–4 (optional) | ~15–75 | Fits small PG if workers careful |
| Lean HA (2 API + 2 AI + 1 outbound) | 2 | 3 | ~75 | Needs PG ≥ `db-s-1vcpu-2gb` class or PgBouncer |
| Growth 5k owners | 4–8 API | 4–12 workers | 120–300 | **Require PgBouncer or resize**; lower per-process pool to 3+2 |

## Recommended per-process pools (launch)

| Role | pool_size | max_overflow |
|------|-----------|--------------|
| API | 3 | 2 |
| AI worker | 2 | 2 |
| Outbound worker | 2 | 2 |
| Request worker | 2 | 2 |

## Resize triggers

| Signal | Action |
|--------|--------|
| PG connections > 70% max sustained 10m | Add PgBouncer or resize PG |
| p95 query > 200ms on hot paths | EXPLAIN + indexes; then resize |
| Lock waits / deadlocks rising | Fix query/transaction scope first |
| Disk > 80% | Storage resize |

## Indexes / query hygiene (code follow-ups)

- Prefer cursor/keyset pagination on Requests lists (already directed in product code).
- Bound scans; avoid N+1 on tenant dashboards.
- Keep WhatsApp SoT fail-closed (no file fallback) — `db/session.py`.

## Non-goals this phase

- No production migration apply
- No destructive EXPLAIN ANALYZE on prod without approval
- Firestore is separate capacity (managed); not in PG budget
