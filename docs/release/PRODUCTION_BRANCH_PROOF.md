# PRODUCTION BRANCH PROOF — FINAL GO/NO-GO

**Repo:** `/Users/alzoughbi/linasbot-server`  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)

## Verdict

```
PRODUCTION_BRANCH_READY
```

## Identity (section 21 return fields)

```
AUDITED_FAIL_HEAD=12e00eb797cd0e774c6948ba5379bc0974837c91
FINAL_RC_SHA=3d0bebdfb30c3856e182ef914cf2b5db862569dd
PROOF_DOCS_SHA=3d0bebdfb30c3856e182ef914cf2b5db862569dd
PR_240_HEAD=3d0bebdfb30c3856e182ef914cf2b5db862569dd
PR_240_CI=rerunning_after_ci_fix
NODE_LOCAL_CRITICAL_STATE=NONE
CURRENT_HEAD=3d0bebdfb30c3856e182ef914cf2b5db862569dd
BRANCH=chore/project-cleanup-reorg
PROOF_DOC=docs/release/FINAL_PROOF_CHECK.md
CUTOVER_DOC=docs/release/PG_CUTOVER_RC.md
FORBIDDEN_HONORED=no_merge_no_deploy_no_requests_migration_no_droplet_boc_off_no_live_sot_flips
```

## What closed the prior FAIL / PARTIAL set

| Prior | Fix |
|-------|-----|
| #8 signedRenewalInfo | `apple_renewal_info.py` + processor wire |
| #9 false `active` | `apple_assn_types.py` explicit map; unknown ignored |
| #10 ASSN 503 without IAP `.p8` | webhook gate removed; JWS-only |
| #12 race / double-apply | claim-before-effect (`apple_notification_claim.py`) |
| #13 cert dates | `_assert_cert_validity` UTC notBefore/notAfter |
| #14 history pagination | `iter_notification_history` + reconcile loop |
| #15 mobile UX | `appleAccount.ts` + Settings + unit tests |
| #16 Apple revoke | AuthKey revoke + meta outbox + drain script |
| #1–4/#17/#18 file defaults | RC defaults → `postgres` + fail-closed + cutover doc |
| Apple grant atomicity | one PG TX when billing=postgres (`apple_credit_grant_ops.py`) |

## Evidence tests (local)

- Backend focused: **79 passed** (Apple ASSN/JWS/revoke/atomic + billing/auth/credits PG + meta + redis fail-closed + financial/inbound invariants)
- Mobile: **5 passed** (`appleAccount.test.mjs`)
- Ruff on touched Apple/billing modules: clean

## Ops readiness (not executed live)

- `docs/release/PG_CUTOVER_RC.md` — alembic, import, parity, defaults, rollback, revoke drain
- Redis require / fail-closed: code ready, **not** enabled on prod
- Requests prod migration: **not** done (forbidden)

## Explicitly not done

- Merge PR #240
- Deploy
- Live prod SoT flag flips beyond code defaults already in tree
- Droplet resize/delete
- BOC enable
- Requests production migration
