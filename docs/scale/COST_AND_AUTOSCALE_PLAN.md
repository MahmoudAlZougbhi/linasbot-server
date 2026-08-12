# Cost and Autoscale Plan — Linas AI

**Date:** 2026-08-12  
**Currency:** USD / month (approximate, DO list prices)

## Monthly infrastructure bands

| Band | Compute | LB | Valkey | Postgres | Spaces | Est. total new+existing |
|------|---------|----|--------|----------|--------|-------------------------|
| Idle / launch LEAN | 1× current ~$24 | $0 | $15 (L) | existing | $0 | **~$39** |
| Normal small | 1× $24–$32 | $0 | $15 | existing | $0–$5 | **~$40–$52** |
| 5k owners target | 2× $32 + workers | $12 | $15→$60 | maybe resize | $5 | **~$100–$160** |
| High social burst | scale workers | $12+ | $60+ | pooled | $5 | pay-as-you-grow |
| Growth stage | pools / maybe DOKS | $12+ | larger | HA PG | $5+ | defer |

Do **not** provision growth-stage resources today.

## LEAN_LAUNCH_MONTHLY (recommended add-now if owner chooses LEAN)

| Item | Cost |
|------|------|
| Existing droplet (keep) | ~$24 (already paying) |
| Valkey OPTION L `db-s-1vcpu-1gb` ×1 lon1 | **+$15** |
| **New spend** | **~$15** |
| **All-in approx** | **~$39** |

## HA_LAUNCH_MONTHLY

| Item | Cost |
|------|------|
| Regional HTTP LB | $12 |
| 2× `s-2vcpu-4gb` | $64 |
| Valkey OPTION HA `db-s-1vcpu-2gb` ×2 | $60 |
| Spaces (if media) | $5 |
| **HA launch estimate** | **~$141** (or ~$136 without Spaces) |

## Autoscale signals

### API scale-out

- CPU > 70% sustained 10m  
- p95 latency > 500ms  
- active connections high  

Min: 1 (LEAN) / 2 (HA). Max: start at 4. Cooldown: 5m. Scale-down only after drain.

### Worker scale-out

- queue depth high  
- oldest event age > 60s  
- worker utilization high  

**Do not** scale AI workers solely on CPU when OpenAI/Meta RPM already saturated — increase queue latency, not replica storms.

### Valkey resize

- memory > 70%  
- evictions > 0  
- failover desire → OPTION HA

## Cost control rules

1. Pay for scale when usage grows.  
2. Provider limits are external — queue safely.  
3. Prefer Droplet Autoscale Pools before DOKS/Kafka.  
4. Kafka/DOKS only with measured justification.
