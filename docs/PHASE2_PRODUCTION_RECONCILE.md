# Phase 2 — Production CM/bridge reconciliation

**Reconciled:** 2026-08-09 (from production CI logs + live `/api/ready`)

## Discrepancy resolution

Earlier Phase 2 report claimed “production CM cutover flags not flipped.”

**That was incorrect relative to the live host.** It reflected the Phase 2 feature-branch *code* not yet being deployed, not the CM cutover env state.

| Check | Actual production evidence |
|-------|----------------------------|
| Deployed SHA (latest Deploy to Production run `31314664732`) | `2b4dad24acb72da4efba7b61023c413faaaac53c` (`2b4dad2` — PR #96 settings cleanup) |
| `CM_DISABLE_LINAS_LEGACY_BRIDGE` effective | **true** (verified in deploy output + `verify_durable_bridge` phase) |
| `linas_has_published_cm` | **true** |
| `tenant_uses_cm_runtime` | **true** |
| Emergency legacy | Use only `CM_EMERGENCY_FORCE_LEGACY=true` — do **not** clear the durable bridge disable flag |
| Phase 2 mobile/Redis/workers on prod | **Not deployed yet** (still feature branch) |

Sources:
- Deploy log `31314664732` (2026-08-09 ~12:59 UTC)
- CM cutover `verify_durable_bridge` run `31313576664`
- Live `GET https://linasaibot.com/api/ready` → `ok:true`

## Rule for all Phase 2 infra work

Never re-enable the legacy bridge. Deploy must continue to call `prod_cm_preserve_durable_flags.sh`.
