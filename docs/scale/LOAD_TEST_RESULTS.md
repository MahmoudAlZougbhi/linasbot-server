# Real-infra load certification results

**Generated:** see `LOAD_TEST_RESULTS_REAL_INFRA.json`  
**Topology:** Managed Valkey HA lon1 + regional LB + app nodes `510629908` + `591901417`  
**Providers:** OpenAI/Meta mocked in harness; Redis/DB/LB real  
**Invariant:** `unexplained_missing_events = 0` (**met**)

## Verdict

**`all_passed=true`**

| Check | Pass |
|-------|------|
| Valkey TLS + replication | yes |
| 5k owners | yes |
| 20k burst + duplicates | yes |
| OOO conversation locks | yes |
| Worker crash retry/DLQ | yes |
| Durable ledger pytest | yes |
| LB health burst + ready sequential | yes |

## Bottlenecks observed

- `/api/ready` too heavy for high concurrency HC (use `/api/health` on LB)
- 2vCPU nodes saturate under parallel ready probes
- Shared Redis rate-limit awaits PR #240 deploy (prod still file RL)
