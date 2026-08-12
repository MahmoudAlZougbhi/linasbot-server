# Runbook (prepare only) — Resize node02 & replace node01

**Status:** PREPARE ONLY — do **not** execute until owner release approval after:
PR #240 deploy → PG soak → registry postgres cutover → billing/auth/credits postgres cutover → failover proof → rollback window.

**Forbidden now:** droplet resize, delete node01, delete node01 local PG, NFS removal live, flag flips on prod.

---

## Preconditions (all must be true)

1. Release candidate merged/deployed with owner approval.
2. Managed PG HA healthy; app DSNs private TLS.
3. `META_REGISTRY_BACKEND=postgres` soaked; `scripts/ha/remove_registry_nfs.sh` applied only after dual→postgres.
4. `LINAS_BILLING_BACKEND=postgres` + `LINAS_AUTH_TOKEN_BACKEND=postgres` soaked (import done).
5. Failover proof: LB drain each node; `unexplained_missing_events=0`; `unexplained_financial_delta=0`.
6. Rollback window still open (node01 local PG retained until owner says otherwise).

---

## Phase A — Resize node02 (2 vCPU / 4GB → 2 vCPU / 2GB)

**Goal:** Cost optimize the clean app node after HA proof.

1. Drain node02 from DO Load Balancer (remove / disable).
2. Confirm node01 alone serves `/api/ready` + Meta/WA webhook smoke.
3. Snapshot node02 droplet.
4. Power off → resize to **s-2vcpu-2gb** (or current DO equivalent) → power on.
5. Verify systemd `linasbot`, Valkey connectivity, Managed PG, Resend SENDING_ONLY fp unchanged.
6. Re-add to LB; smoke auth refresh, webhook verify, email send.
7. Durability: inbound reconcile `unexplained_missing_events=0`.

**Rollback:** Restore from snapshot or scale back up; keep node01 in LB.

---

## Phase B — Replace legacy node01 with clean 2 vCPU / 2GB app replica

**Goal:** Remove node01 SPOF legacy (local PG / NFS history) after soak.

1. Provision **new** droplet `linas-app-lon1-01b` (2 vCPU / 2GB) from known-good image / ansible / deploy script — **do not** mutate old node01 in place first.
2. Install app + `.env` (copy secrets; mode `0600`); no Full Access Resend.
3. Point DSN to Managed PG; Redis to Valkey HA; no NFS mounts for registry/media.
4. Health green on private IP; add behind LB as third member briefly **or** swap after drain.
5. Drain old node01; soak; prove failover.
6. Only then (separate owner GO): decommission old node01 droplet + local PG.

**Do not** delete node01 local PostgreSQL until owner explicitly approves after Managed PG soak.

---

## Evidence to capture

- LB target health before/after
- `/api/ready` on each node
- Resend key fp (SENDING_ONLY) + mode `0600`
- `unexplained_missing_events=0`
- `unexplained_financial_delta=0` on financial smoke
- Registry backend env value

---

## Related scripts/docs

- `scripts/ha/verify_multi_node_closeout.sh`
- `scripts/ha/power_loss_simulation.sh`
- `scripts/ha/remove_registry_nfs.sh` (post-postgres only)
- `docs/scale/COST_OPTIMIZATION_AUDIT.md`
- `docs/scale/HA_NODE01_SPOF_HARDENING.md`
