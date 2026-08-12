# Load Test Results — Linas AI (synthetic / mocked providers)

**Generated:** 2026-08-12T15:31:17Z  
**Run ID:** `d89bdd79c5254b95ad4a03063925c4ac`  
**Topology under test:** `local_fakeredis_synthetic`  
**All passed:** **True**

> These results certify queue/claim/lock/backpressure/drain behavior with **fakeredis** and mocked provider delays.
> They do **not** claim live production 100k GPT replies or real Meta throughput.

| Scenario | Concurrency | Events | Accepted | Dupes | Lost | Ord fail | Err | p50ms | p95ms | p99ms | Pass |
|----------|-------------|--------|----------|-------|------|----------|-----|-------|-------|-------|------|
| A_mobile_owners | 100 | 100 | 100 | 0 | 0 | 0 | 0 | 6.1 | 6.4 | 6.6 | True |
| A_mobile_owners | 500 | 500 | 500 | 0 | 0 | 0 | 0 | 6.8 | 7.9 | 8.3 | True |
| A_mobile_owners | 1000 | 1000 | 1000 | 0 | 0 | 0 | 0 | 7.1 | 8.4 | 8.9 | True |
| A_mobile_owners | 2500 | 2500 | 2500 | 0 | 0 | 0 | 0 | 7.5 | 11.1 | 12.0 | True |
| A_mobile_owners | 5000 | 5000 | 5000 | 0 | 0 | 0 | 0 | 7.8 | 13.7 | 16.2 | True |
| B_customer_ingress | 64 | 2000 | 1820 | 180 | 0 | 0 | 0 | 18.2 | 21.1 | 24.0 | True |
| C_100k_conversations | 128 | 20000 | 19601 | 399 | 0 | 0 | 0 | 10.9 | 56.4 | 95.7 | True |
| D_provider_slowdown | 1 | 200 | 30 | 0 | 0 | 0 | 0 | 53.5 | 55.5 | 57.9 | True |
| E_node_failure_drain | 1 | 100 | 40 | 0 | 0 | 0 | 0 | 0.1 | 0.4 | 0.7 | True |

## Derived capacity (this harness)

- **5k concurrent owner synthetic (Scenario A @ 5000):** passed locally for coordinator/session-shaped work — **not** a claim that the current 2GB droplet serves 5k live users.
- **100k conversation identity pool (Scenario C):** burst over conversation keys with no loss/ordering failure under fakeredis — proves **control-plane** safety, not provider TPS.
- **Provider bottleneck:** Scenario D shows RPM/inflight backpressure blocks excess OpenAI-shaped calls without errors.
- **Safe measured claim:** durable enqueue + idempotent claims + conversation locks + drain requeue work under synthetic load.

## Failure point (current prod topology)

Live prod still has unreachable Redis and a single 2vCPU/2GB droplet — **production safe capacity remains far below 5k owners** until Valkey + compute/LB purchases land.
