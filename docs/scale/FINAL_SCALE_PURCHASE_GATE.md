# FINAL SCALE PURCHASE GATE — Linas AI

**Date:** 2026-08-12  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Status:** `HA_INFRA_COMPLETE — AWAITING APP RELEASE / REQUESTS MIGRATION APPROVAL`  
**Do NOT merge until OWNER GO for release. Do NOT apply Requests prod migration yet. BOC OFF.**

Companion: [`HA_PURCHASE_EXECUTION.md`](./HA_PURCHASE_EXECUTION.md)

## Live HA purchase (executed)

| Item | Live | Cost |
|------|------|------|
| Valkey 8 lon1 `db-s-1vcpu-2gb` ×2 | `linas-redis-prod` online | **$60** |
| Regional LB lon1 1 node | `linas-http-lb-lon1` `157.245.31.104` | **$12** |
| Second app `s-2vcpu-4gb` | `linas-app-lon1-02` | **$24** |
| Spaces | skipped | **$0** |
| **NEW monthly** | | **`$96`** |

## Cert summary

- Valkey TLS/auth + standby replication: **PASS**
- LB + two nodes + DNS cutover: **PASS**
- One-node failure (LB continues): **PASS**
- Real-infra load cert (`LOAD_TEST_RESULTS_REAL_INFRA.json`): **`all_passed=true`**, `unexplained_missing_events=0`
- Shared Redis rate-limit / drain-503 / ledger-in-webhook: **code on PR #240 only** — not live until deploy

## Ready for Requests migration + prod deploy?

**Infra: YES.** **App release / Requests migration: NO** until OWNER explicitly approves merge+deploy of #240 and worker flag policy.
