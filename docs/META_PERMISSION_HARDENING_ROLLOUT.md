# Meta permission hardening — rollout gates (owner approval required)

> **Do not deploy to production without explicit owner approval.**  
> **Do not Submit App Review yet.**

This checklist applies after [PR #542](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/542)
(comment permission hardening) is merged.

---

## Phase 0 — Before any production deploy

| Step | Action | Gate |
|------|--------|------|
| 0.1 | **Merge PR #542** to `main` | PR approved |
| 0.2 | Wait for **CI green on `main`** | All quality-gates pass |
| 0.3 | Note **`main` merge SHA** (not the PR tip SHA) | e.g. `git rev-parse origin/main` |
| 0.4 | Owner fills Dashboard compliance URLs | `docs/META_DASHBOARD_COMPLIANCE_AND_DRAFT_CHECKLIST.md` § Part 1 |
| 0.5 | Owner opens Meta Support ticket (comments delivery) | `docs/META_SUPPORT_TICKET_COMMENTS_NOT_DELIVERED.md` |
| 0.6 | **No App Review Submit** until comment delivery + recordings exist | — |

---

## Phase 1 — Protected HA deploy (no manual SSH alembic/backfill)

Deploy **only** the final **`main` merge SHA** via the existing protected workflow:

`.github/workflows/deploy.yml` → `scripts/ha/deploy_meta_release_ha.sh`

### What HA deploy already runs (authorized path)

1. Drain both nodes / maintenance gate
2. Transient target verification API
3. **`run_target_alembic_migrate`** → `scripts/ha/release_alembic_migrate.py`  
   (systemd `linasbot-ha-alembic-migrate.service`, `LINAS_HA_VERIFY_RELEASE_SHA` pinned)
4. Readiness probe
5. LB admission only after parity

**Expected DB revision after migrate:** `20260826_meta_comment_perm`  
Verify on both nodes after deploy: `alembic current`

### What must run in the same protected window (before LB)

After Alembic migrate, **before any node enters the load balancer**:

```text
scripts/ha/run_meta_comment_permission_backfill.py
  → scripts/backfill_meta_comment_permission_verification.py
```

**Not allowed:** manual `alembic upgrade`, manual backfill over SSH, or editing `.env` on one node only.

### Backfill hard stop

The backfill helper exits **2** if any **active** binding remains
`comment_permission_status=unknown` after apply.

**If exit 2:** stop deploy — **do not** attach either node to LB. Investigate binding
scopes/credentials before retrying.

Dry-run (still inside HA verify window):

```bash
LINAS_HA_COMMENT_BACKFILL_DRY_RUN=true \
LINAS_HA_VERIFY_RELEASE_SHA=<merge_sha> \
/opt/linasbot/venv/bin/python -B -I scripts/ha/run_meta_comment_permission_backfill.py
```

---

## Phase 2 — Post-deploy parity proof

On **node01** and **node02** (same merge SHA):

```bash
git -C /opt/linasbot rev-parse HEAD          # identical merge SHA
alembic current                               # 20260826_meta_comment_perm
```

Functional smoke (device + dashboard):

| Surface | Expected |
|---------|----------|
| Facebook DM | Works (unchanged path) |
| Instagram DM | Works (unchanged path) |
| Facebook Comments capability | **Not `unknown`** after backfill; enforcement uses stored verification |
| Facebook Comments AI reply | Only if Meta delivers comment data (separate Meta issue) |

---

## Phase 3 — Compliance verification (not App Review submit)

Live routing + signed **rejection** (safe, no secrets):

```bash
python scripts/verify_meta_compliance_urls.py
```

Full Meta signed_request contract (valid POST, wrong signature, deletion confirmation JSON):

```bash
python scripts/verify_meta_compliance_urls.py --pytest-contract
# equivalent: pytest tests/test_meta_compliance.py -q
```

**HTTP 200 alone does not prove Deauthorize/Data Deletion work.**

---

## Phase 4 — App Review draft (later; separate FB / IG if needed)

Do **not** blindly keep “exactly 10 permissions”. Request only permissions that are:

1. **Used** by the runtime for the recorded flow, and  
2. **Proven** in the attached screencast for that permission family.

Prefer **separate evidence sections** (Facebook Page/Messenger vs Instagram Login) in one
top-level draft, or **separate submissions** if Meta test paths diverge.

Draft cleanup guide: `docs/META_DASHBOARD_COMPLIANCE_AND_DRAFT_CHECKLIST.md` § Part 2

---

## Explicit non-goals

- Does not fix Meta Graph `comments` returning `data:[]` or missing comment webhooks
- Does not Submit App Review
- Does not change DM / Connect / webhook subscription fields
