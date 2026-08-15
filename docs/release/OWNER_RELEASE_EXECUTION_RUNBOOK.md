# Owner release execution runbook — PR #240

**Status:** OWNER-APPROVED EXECUTION PLAN ONLY  
**Rules for this document:** plan + commands. **Do not** treat reading this file as authorization to mutate production until Mahmoud explicitly says GO for each phase.

| Field | Value |
|-------|--------|
| Repo | `/Users/alzoughbi/linasbot-server` |
| PR | [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240) (`chore/project-cleanup-reorg` → `main`) |
| `FINAL_RC_SHA` | `b3f428475325860a2252e6a0cf33776d7e81c4ea` |
| Proof | `docs/release/PRODUCTION_BRANCH_PROOF.md` + `docs/release/FINAL_PROOF_CHECK.md` → `PRODUCTION_BRANCH_READY` |
| Cutover detail | `docs/release/PG_CUTOVER_RC.md` |
| Apple handoff | `docs/release/APPLE_INTEGRATION_COMPLETE.md` |
| Droplet resize | **OUT OF SCOPE for this release** — prepare-only: `docs/scale/RUNBOOK_RESIZE_REPLACE_NODE01_PREPARE.md` |
| BOC | **OFF** — never set `LINASLASER_BOC_BOOKING_ENABLED=true` |

**SHA note:** `FINAL_RC_SHA` is the last green **implementation** tip (Apple ASSN/auth/PG cutover + CI). Later **docs-only** commits may advance `PR_240_HEAD` without changing the freeze. Mobile store builds **must** pin `FINAL_RC_SHA`. Server merge may include docs after that SHA.

**Verify tip before GO:**

```bash
cd /Users/alzoughbi/linasbot-server
git fetch origin
git rev-parse origin/chore/project-cleanup-reorg
# Expect FINAL_RC_SHA as ancestor:
git merge-base --is-ancestor b3f428475325860a2252e6a0cf33776d7e81c4ea origin/chore/project-cleanup-reorg && echo FINAL_RC_OK
```

---

## 0. Preconditions (all required before merge)

1. Mahmoud explicit **GO merge #240**.
2. PR #240 CI green (backend · frontend · mobile · secret-scan · deploy-readiness).
3. Managed Postgres HA `linas-postgres-prod` healthy; both app nodes already use `LINAS_WHATSAPP_DATABASE_URL` → private Managed PG (`:25060`).
4. Managed Valkey `linas-redis-prod` reachable for `REDIS_URL` / `RATE_LIMIT_REDIS_URL` (purchase already done per cost audit — **do not** flip require/fail-closed yet).
5. DigitalOcean / Managed PG **backup or snapshot** taken and noted (timestamp + ID).
6. Record **live production SHA before merge** (rollback target):

```bash
# On a prod node (or from last successful Deploy workflow log):
cd /opt/linasbot && git rev-parse HEAD
# Also note: https://github.com/MahmoudAlZougbhi/linasbot-server/actions (Deploy to Production → last green commit)
```

7. Billing/auth may retain their own file pins until their imports complete. For
   Meta, the 2026-08-14 inventory supersedes this historical step: Managed PG is
   already newer/authoritative, so **never pin Meta to the stale file**. Stage
   explicit `META_REGISTRY_BACKEND=postgres` identically on both nodes through the
   transactional env/deploy procedure:

```bash
# Exact lines to ADD (or keep) until import+parity complete — names only; no secrets:
LINAS_BILLING_BACKEND=file
LINAS_AUTH_TOKEN_BACKEND=file
META_REGISTRY_BACKEND=postgres
```

8. Apple `.p8` files present on nodes at protected `0600` paths (or deploy secrets in the same window as ASSN enablement) — see §9. Do **not** commit keys.

---

## 1. Exact merge order for PR #240

1. Confirm preconditions in §0.
2. Confirm `FINAL_RC_SHA=b3f428475325860a2252e6a0cf33776d7e81c4ea` is an ancestor of the PR tip.
3. In GitHub: open [PR #240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240) → **Merge** into `main` (use the repository’s normal protected merge method — no force-push).
4. Record the **merge commit SHA** on `main` (this is the deploy SHA Quality Gates / Deploy will use).
5. Do **not** merge any other PR in the same window unless Mahmoud approves.
6. Do **not** enable BOC, Requests migration, droplet resize, or Redis require flags at merge time.

---

## 2. Exact deployment order

Merge to `main` automatically drives:

```text
push/merge → main
  → workflow "Quality Gates" (.github/workflows/quality-gates.yml)
    → on success → workflow "Deploy to Production" (.github/workflows/deploy.yml)
      → SSH → /opt/linasbot
      → backup data/ → git fetch origin main → git reset --hard origin/main
      → sudo bash /opt/linasbot/deploy.sh
```

**Operator sequence (exact):**

| Step | Action | Gate |
|------|--------|------|
| A | Merge #240 (§1) | PR merged |
| B | Watch **Quality Gates** on `main` for the merge SHA | All jobs SUCCESS |
| C | Watch **Deploy to Production** (`workflow_run` after gates) | SSH Deploy SUCCESS |
| D | Confirm both LB backends healthy | `https://linasaibot.com/api/health` → 200; LB target health green |
| E | Confirm exact canonical env parity; Meta explicitly `postgres` | §0.7 + Meta HA runbook |
| F | Apply Alembic **only through Apple** (§3) on Managed PG | `alembic current` = `20260812_apple_billing` |
| G | Billing/auth import per their runbooks; Meta PG backup + read-only deep verify (§3) | no Meta file import |
| H | Billing/auth cutover per their runbooks; keep explicit `META_REGISTRY_BACKEND=postgres` on both nodes (never `dual`) | env updated |
| I | Restart app on both nodes (`systemctl restart linasbot` or redeploy) | `/api/ready` ok |
| J | Post-deploy smoke (§6) | all checks pass |
| K | Soak window (owner-chosen duration; recommend ≥24h of normal traffic) | no financial/auth regressions |
| L | Post-soak production flags (§4) | Redis require / fail-closed only after soak GO |
| M | Mobile: TestFlight + Android Internal from `FINAL_RC_SHA` (§7–§8) | builds uploaded |
| N | External Apple / Google console actions (§9–§10) | owner ASC / Play UI |

**Forbidden in this release window:**

- `workflow_dispatch` emergency deploy unless incident (`EMERGENCY_DEPLOY_CONFIRM=I_UNDERSTAND_SKIPPING_GATES`)
- Droplet resize / delete / NFS removal (`docs/scale/RUNBOOK_RESIZE_REPLACE_NODE01_PREPARE.md` stays prepare-only)
- Requests Alembic past Apple (§3 “do not run”)
- `LINASLASER_BOC_BOOKING_ENABLED=true`

---

## 3. Exact migrations to run

### Chain (linear)

```text
… → 20260811_wa_app_review_source   (already on main / prod baseline)
  → 20260812_meta_app_registry
  → 20260812_ha_billing_auth
  → 20260812_credit_entitlements
  → 20260812_apple_billing          ← STOP HERE for this release
  → 20260812_customer_requests      ← DO NOT RUN YET (Requests separate)
  → 20260812_outbox_processing      ← DO NOT RUN YET
  → 20260812_outbox_claim_lease     ← DO NOT RUN YET
```

### When (relative to deploy)

1. **After** Deploy SUCCESS puts this branch’s Alembic files on disk.
2. **While** billing/auth retain their approved file pins, but Meta is explicitly
   `META_REGISTRY_BACKEND=postgres` (§0.7 and the Meta HA runbook).
3. **Before** removing billing/auth pins; never unset or switch Meta to stale file/dual.

### Exact commands (Managed PG via app env)

```bash
# On a prod app node as root/deploy user with venv + env loaded:
cd /opt/linasbot
set -a && source /opt/linasbot/.env && set +a
source venv/bin/activate   # or the active deploy venv path after deploy.sh

# APPLY ONLY THROUGH APPLE — do NOT use upgrade head / heads
python -m alembic upgrade 20260812_apple_billing
python -m alembic current
# Expect: 20260812_apple_billing (head of applied chain for this release)
```

**Do not run:**

```bash
python -m alembic upgrade head          # FORBIDDEN — pulls Requests + outbox
python -m alembic upgrade heads         # FORBIDDEN for this window
bash scripts/prod_whatsapp_cloud_migrate.sh   # FORBIDDEN — script runs `alembic upgrade head`
```

### Import + parity (after migrations, still before postgres cutover)

```bash
cd /opt/linasbot
set -a && source /opt/linasbot/.env && set +a
source venv/bin/activate

python scripts/ha/import_billing_auth_to_postgres.py --dry-run
python scripts/ha/import_billing_auth_to_postgres.py

python scripts/ha/verify_billing_auth_parity.py
```

**2026-08-14 Meta registry safety override:** do not run the old file import or
an “idempotent” re-import. Managed Postgres is non-empty/newer and NFS is stale.
Follow `docs/scale/META_REGISTRY_POSTGRES_HA_CUTOVER.md`; the guarded importer is
dry-run by default and intentionally refuses the observed production shape.

Then complete §2 steps H–J (unset file pins → restart → smoke).

### Apple revoke outbox (after secrets wired)

```bash
python scripts/ha/process_apple_revoke_outbox.py
python scripts/ha/process_apple_revoke_outbox.py --limit 50
```

---

## 4. Exact production flags to enable after soak

Enable **only after** Mahmoud soak GO and §6 smoke remains green.

### A. Postgres SoT (expected steady state)

After the current Postgres authority is backed up and verified, on **both** nodes:

- Set exact steady-state flags; `META_REGISTRY_BACKEND` must be explicit because
  an omitted default is not sufficient for NFS retirement:
  - `LINAS_BILLING_BACKEND=postgres`
  - `LINAS_AUTH_TOKEN_BACKEND=postgres`
  - `META_REGISTRY_BACKEND=postgres`
- Do **not** leave `=file` or long-lived `=dual` (dual is migration helper only).

Restart `linasbot` on both nodes after env change.

### B. Redis require / fail-closed (post-soak; code ready, currently off)

Only when Valkey is proven reachable and multi-worker rate-limit smoke passed:

```bash
# Exact flag names:
LINAS_FAIL_CLOSED_REDIS_CLAIMS=true
LINAS_REQUIRE_REDIS=true
```

Order: enable `LINAS_FAIL_CLOSED_REDIS_CLAIMS` first (or together), confirm `/api/ready` still ok, then keep `LINAS_REQUIRE_REDIS=true` only if durable queue requirement is intended.

### C. Remain OFF / do not set

| Flag / action | Value |
|---------------|--------|
| `LINASLASER_BOC_BOOKING_ENABLED` | unset / `false` |
| Requests Alembic `20260812_customer_requests` (+ outbox) | **not applied** |
| Droplet resize / node01 delete | **not executed** |
| Emergency gate bypass deploy | **not used** |

---

## 5. Exact rollback steps

### A. Application code rollback (fast)

```bash
# On each prod node (or let a follow-up deploy land the prior SHA):
cd /opt/linasbot
PREVIOUS_PROD_SHA=<sha recorded in §0.6>
git fetch origin
git reset --hard "$PREVIOUS_PROD_SHA"
sudo bash /opt/linasbot/deploy.sh
```

Confirm: `https://linasaibot.com/api/health` and `/api/ready`.

### B. SoT / flag rollback (if postgres cutover misbehaves)

```bash
# Billing/auth emergency rollback only; Meta has a separate PG snapshot rollback.
LINAS_BILLING_BACKEND=file
LINAS_AUTH_TOKEN_BACKEND=file
```

Never enable or re-import the stale Meta NFS file. Follow the registry-only
encrypted four-table restore in `docs/scale/META_REGISTRY_POSTGRES_HA_CUTOVER.md`.

Apple transaction / credit-grant **tables** remain Postgres regardless of billing flag.

### C. Redis flag rollback

```bash
# Unset or set false:
# LINAS_REQUIRE_REDIS=
# LINAS_FAIL_CLOSED_REDIS_CLAIMS=
```

Restart. Rate limits may become process-local again — acceptable only briefly.

### D. Migrations

- This release’s revisions are **additive**. Prefer **forward-fix** over downgrade.
- Do **not** run Requests downgrade (Requests never applied).
- Only if Mahmoud explicitly orders: `alembic downgrade 20260811_wa_app_review_source` drops the new meta/billing/apple tables — destructive; take a fresh PG backup first.

### E. Mobile

- Pause TestFlight / Play Internal rollout; do not promote to production store tracks.
- Users keep prior installed build; no server rollback required for mobile-only issues unless API contract broke.

---

## 6. Exact smoke tests after deploy

Run after §2 I (postgres cutover restart) and again after §4 Redis flags.

```bash
# Liveness / readiness
curl -fsS https://linasaibot.com/api/health
curl -fsS https://linasaibot.com/api/ready
# Expect ok:true; boc_booking must NOT require BOC; redis_required false until §4

# Public site / dashboard shell
curl -fsSI https://linasaibot.com/ | head -n 5
```

**Auth / billing / registry**

- Mobile refresh token path works for a test account (login → refresh → authenticated API).
- Dashboard login + one authenticated read.
- Confirm billing/entitlement read does **not** 5xx when PG is up (fail-closed only if PG down).

**WhatsApp / Meta (VERIFY_AND_PRESERVE — no rebuild)**

- WA webhook verify challenge still 200 with good token / 403 bad.
- Meta messaging webhook path still authenticated (no disconnect/rebuild).

**Apple (once secrets + ASC URL registered)**

- `POST` ASSN TEST notification from App Store Connect → 2xx; row in `apple_notification_events`.
- Optional: Sandbox purchase → credit/entitlement once; repeat → no double grant.
- Account delete → revoke outbox attempts; drain with `process_apple_revoke_outbox.py`.

**Invariants**

```bash
# Use existing HA / scale verification tooling available on the node, e.g.:
bash scripts/ha/verify_multi_node_closeout.sh
# Require:
#   unexplained_missing_events = 0
#   unexplained_financial_delta = 0
```

**Mail (if Resend already wired)**

- `/api/ready` mail check; one transactional test send (see `docs/release/RESEND_PRODUCTION_SECRETS.md`).

**Negative**

- With postgres backends and PG stopped (maintenance drill only): requests must **fail closed** (no silent file SoT).

---

## 7. Exact TestFlight build steps from `FINAL_RC_SHA`

Pin **exactly** `b3f428475325860a2252e6a0cf33776d7e81c4ea` (not a later docs-only tip).

```bash
cd /Users/alzoughbi/linasbot-server
git fetch origin
git checkout b3f428475325860a2252e6a0cf33776d7e81c4ea

cd mobile/linas-ai
npm ci
npm run prebuild:check
npm run secret-scan

# Identity
# Bundle: com.linasai.app
# ASC App ID: 6799678918
# EAS project: d15fe78a-09df-4d7c-81a5-2b307956fddf
# Profile: testflight (extends production; EXPO_PUBLIC_API_BASE_URL=https://linasaibot.com)

# If ASC/EAS build numbers drifted:
eas build:version:set -p ios

eas build --platform ios --profile testflight --non-interactive
eas submit --platform ios --profile testflight --latest --non-interactive
```

Then in App Store Connect → TestFlight → add internal/external testers → install on device → run Sandbox SIWA + IAP matrix (Expo Go is **blocked** for IAP).

---

## 8. Exact Android Internal Testing AAB steps from same SHA

Same checkout as §7 (`FINAL_RC_SHA`).

```bash
cd /Users/alzoughbi/linasbot-server
git checkout b3f428475325860a2252e6a0cf33776d7e81c4ea
cd mobile/linas-ai
npm ci

# Package: com.linasai.app
# Profile production → android.buildType = app-bundle (AAB)
# Env: EXPO_PUBLIC_API_BASE_URL=https://linasaibot.com

eas build:version:set -p android   # if Play/EAS versionCode drift
eas build --platform android --profile production --non-interactive
```

**Upload to Google Play Internal Testing**

1. Download the AAB from the EAS build page (or `eas build:list` → artifact URL).
2. [Google Play Console](https://play.google.com/console) → app **Linas AI** (`com.linasai.app`) → **Testing** → **Internal testing**.
3. Create/select release → upload AAB → review → rollout to internal testers.
4. License testers: add accounts under **Setup → License testing**.
5. Install from Play Internal track (not Expo Go) → smoke auth + billing UI.

Optional if Play submit credentials are already configured in EAS:

```bash
eas submit --platform android --latest --non-interactive
# Then still promote/assign the release on the Internal testing track in Play Console.
```

---

## 9. Remaining Apple external actions

Owner / ASC UI (code is ready; these are **not** done by merge/deploy alone):

1. **Register ASSN V2 URLs** (after HTTPS deploy of this code):
   - Production: `https://linasaibot.com/webhooks/apple/app-store`
   - Alias: `https://linasaibot.com/api/webhooks/apple/app-store`
   - Legacy alias: `https://linasaibot.com/api/entitlements/apple/notifications`
   - Sandbox field: same paths with Sandbox environment selected  
   **Click path:** My Apps → Linas AI → App Store Server Notifications → Version 2 → Save → send **TEST** notification.
2. **Deploy Apple secrets** to both HA nodes (`0600` paths; never commit):

```text
APPLE_TEAM_ID=55624L5UXL
APPLE_BUNDLE_ID=com.linasai.app
APPLE_SIGN_IN_KEY_ID=5FK9G38WRJ
APPLE_SIGN_IN_PRIVATE_KEY_PATH=<protected 0600 path>
APPLE_IAP_ISSUER_ID=a3b052c7-c0ed-4935-8e2e-4b57946e1f6b
APPLE_IAP_KEY_ID=8H9SZG552B
APPLE_IAP_PRIVATE_KEY_PATH=<protected 0600 path>
```

3. **Interactive Sandbox matrix** on TestFlight/dev client (SIWA link/unlink/delete, purchase, restore, refund sheet).
4. **Higher Price Point** request for **Pro Yearly** + **Scale Yearly**; after Apple approval, set real yearly prices — do **not** ship fake lower yearly prices.
5. **App Review screenshots** from real purchase UI.
6. Keep subscription group `22305050` / product map as in `APPLE_INTEGRATION_COMPLETE.md`.

---

## 10. Remaining Google external actions

Owner / Play Console (independent of Apple; package `com.linasai.app`):

1. Confirm Play app exists for package `com.linasai.app` (create if missing).
2. Create matching subscription products + base plans (prices aligned with Apple where applicable).
3. Enable **Play Developer API** + **Real-time developer notifications** (Pub/Sub).
4. Create service account with Android Publisher access; place JSON on server (`0600`); set:
   - `GOOGLE_PLAY_PACKAGE_NAME=com.linasai.app`
   - `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_PATH=<protected path>`
5. Bridge RTDN to: `https://linasaibot.com/api/entitlements/google/notifications`
6. Upload Internal Testing AAB (§8); add license testers; purchase each SKU; confirm entitlement transitions.
7. Do **not** invent a public Play Store URL until the listing is actually live.

---

## Out of scope (explicit)

| Item | Doc / note |
|------|------------|
| Droplet resize node02 / replace node01 | `docs/scale/RUNBOOK_RESIZE_REPLACE_NODE01_PREPARE.md` — after PG+registry+billing soak + failover proof |
| Cost topology changes | `docs/scale/COST_OPTIMIZATION_AUDIT.md` — audit only |
| Requests domain go-live | Separate owner GO + `alembic upgrade` past `20260812_apple_billing` |
| BOC booking | Remains OFF |

---

## One-page GO checklist

```text
[ ] §0 preconditions + file SoT pins + PG backup + PREVIOUS_PROD_SHA recorded
[ ] §1 Merge PR #240
[ ] §2 Quality Gates SUCCESS → Deploy SUCCESS
[ ] §3 alembic upgrade 20260812_apple_billing ONLY + import + parity
[ ] §2 H–J unset file pins → restart → smoke
[ ] §6 smoke green; invariants = 0
[ ] §4 soak GO → postgres steady + optional Redis flags
[ ] §7 TestFlight from b3f428475325860a2252e6a0cf33776d7e81c4ea
[ ] §8 Android Internal AAB from same SHA
[ ] §9 Apple ASC URLs + secrets + Sandbox + Higher Price Point
[ ] §10 Google Play products + RTDN + service account + license tests
[ ] Requests / BOC / droplet resize still NOT done
```
