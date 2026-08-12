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
FINAL_RC_SHA=b3f428475325860a2252e6a0cf33776d7e81c4ea
PR_240_HEAD=b3f428475325860a2252e6a0cf33776d7e81c4ea
PR_240_CI=SUCCESS (backend, frontend, mobile, secret-scan, deploy-readiness)
NODE_LOCAL_CRITICAL_STATE=NONE
CURRENT_HEAD=b3f428475325860a2252e6a0cf33776d7e81c4ea
BRANCH=chore/project-cleanup-reorg
PROOF_DOC=docs/release/FINAL_PROOF_CHECK.md
CUTOVER_DOC=docs/release/PG_CUTOVER_RC.md
FORBIDDEN_HONORED=no_merge_no_deploy_no_requests_migration_no_droplet_boc_off_no_live_sot_flips
```

Note: `FINAL_RC_SHA` is the last fully green implementation tip (ASSN/auth/PG cutover + CI lint/mypy fixes). Later docs-only commits may advance `PR_240_HEAD` without changing that freeze.

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
- Mobile: **113 passed** (`npm test` including `appleAccount.test.mjs`)
- PR #240 CI @ `b3f4284`: **all SUCCESS**

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
