# Phase 13 — Production preparation report (Linas AI)

**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Rule:** No merge, no deploy, no prod migration apply, no live Redis activation, no nginx/systemd reload, no secret rotate, no Meta disconnect/rebuild.  
**BOC:** remains **OFF**.

---

## Executive return

| Gate | Status |
|------|--------|
| Redis | **BLOCKED_PURCHASE** |
| Meta VERIFY_AND_PRESERVE | **VERIFIED** (live) — optional GHA-secret hygiene note below |
| Postgres backup plan | **READY** |
| Requests migration `20260812_customer_requests` | **READY_TO_APPLY** (not applied) |
| nginx | **READY** (functional; full live↔repo byte-diff limited without local SSH) |
| systemd | **READY** (read-only) |
| Firestore indexes | **READY** (no deploy required for this cutover; dry-run OK) |
| Current production SHA | `781a94ca3d50b02b6a8da1b0afeaeaa32e01bb26` |
| PR #240 head (origin tip at report prep) | `768ebe7b93c1e4e770e50fab6faf1f9dcc1f63b0` — CI **GREEN** |
| Freeze SHA (Phase 12 app) | `9757d014dbaca0bfc0b84e9a48133356fdc14958` |

---

## A. Redis / Valkey

### DigitalOcean inventory (doctl, this account)

| Cluster | Engine | Region | Size | Status | Product fit for Linas |
|---------|--------|--------|------|--------|------------------------|
| `sportbook-redis-prod` | Valkey 8 | **fra1** | `db-s-1vcpu-1gb` | online | **No** — SportBook-named; firewall allows SportBook droplets (+ one unrelated fra1 droplet). **Not** Linas lon1. |
| `sportbook-postgres-prod` | Postgres 18 | fra1 | `db-s-1vcpu-2gb` | online | SportBook only (not Linas WA Postgres) |

**No managed Redis/Valkey named or dedicated for Linas production.**

### Linas production host

- DNS `linasaibot.com` → `139.59.167.62`
- Droplet: `ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01` (ID `510629908`, **lon1**)
- Local SSH keys: **Permission denied** (prod SSH only via GitHub Actions secrets)

### Live Redis wiring (read-only)

`GET https://linasaibot.com/api/ready`:

- `job_queue.backend=redis`
- `redis_configured=true`
- `redis_reachable=false` (`ConnectionError`)
- `redis_required=false` → readiness still `ok:true` today
- `production_ready=false`

Interpretation: a Redis URL is set in prod env, but the endpoint is **unreachable**. Must **not** flip `LINAS_REQUIRE_REDIS=true` or rely on rate-limit Redis backend until a reachable cluster exists. Do **not** share SportBook Valkey (wrong product + wrong region).

### BLOCKED_OWNER_ACTION — purchase

Approve creating a **dedicated** DigitalOcean Managed Database:

| Field | Exact value |
|-------|-------------|
| Product | **Managed Databases → Valkey** (Redis-compatible) |
| Name | `linas-redis-prod` |
| Region | **lon1** (same as Linas droplet) |
| Size / plan | **`db-s-1vcpu-1gb`** (1 vCPU / 1 GiB, single node) |
| Version | Valkey **8** |
| Nodes | **1** |
| Monthly cost | **~$15.00 USD / month** (DO docs: single-node Valkey begins at $15.00/mo for 1 GiB) |
| DO UI path | Control Panel → **Databases** → **Create Database Cluster** → Engine **Valkey** → Region **London (lon1)** → Plan **Basic $15/mo (1 GB)** → name `linas-redis-prod` → Create |
| CLI (after approval) | `doctl databases create linas-redis-prod --engine valkey --region lon1 --size db-s-1vcpu-1gb --num-nodes 1 --version 8` |

**After purchase (still owner-gated before live activate):**

1. Trusted sources firewall: allow droplet `510629908` only.
2. Set prod env (names only): `RATE_LIMIT_REDIS_URL` and/or `REDIS_URL` to the **TLS + auth** private/public URI (rediss / `ssl=true`). Prefer `RATE_LIMIT_REDIS_URL` for rate limits; keep prefixes (`linas:rl`).
3. Do **not** enable `LINAS_REQUIRE_REDIS` without separate owner approval (durable queues remain opt-in).
4. Multi-worker smoke (post-wiring, still not a silent fallback): hit rate-limited route from ≥2 workers; confirm shared counters; stop Redis briefly and confirm **fail-closed** (503 / deny), not file/memory fallback.
5. Rollback: unset require flag / restore previous URL values from backup note (never commit secrets).

---

## B. Meta VERIFY_AND_PRESERVE

### Live production (no Meta mutation)

| Check | Evidence | Result |
|-------|----------|--------|
| `/api/ready` meta_social_messaging | app_a configured; FB+IG App A active; credentials valid; App B not active | **OK** |
| Prod Preflight Readonly | run [31604899975](https://github.com/MahmoudAlZougbhi/linasbot-server/actions/runs/31604899975) `COMPLETE_OK` | **OK** |
| Webhook challenge (meta + WA) | good=200 / bad=403; public+local; nginx query hardening | **OK** |
| Meta App A Scope Audit | run [31604922810](https://github.com/MahmoudAlZougbhi/linasbot-server/actions/runs/31604922810) `SUCCESS` | **OK** |
| Comment runtime probe | run [31604926038](https://github.com/MahmoudAlZougbhi/linasbot-server/actions/runs/31604926038) `SUCCESS`; nginx meta-messaging POSTs observed | **OK** |
| Runtime diagnostics | `meta_webhook_authenticated=124` (IG+FB page objects) in recent window | **OK** |

**Scope snapshot (bindings, redacted):**

- Active bindings: **3**
- Facebook DM: effective_enabled=True (messaging scopes present)
- Instagram DM: effective_enabled=True
- Instagram comments (Instagram Login binding): comment_features_ready=True; subscribed_fields include `comments,messages,messaging_postbacks`
- Facebook comments: effective_enabled=False (`missing_comment_permissions`) — **preserve**; not a Phase 13 disconnect/rebuild trigger
- WA Cloud webhook verify path responds correctly; inbound AI remains **disabled**

### Meta Social Token Validate (GitHub secrets only)

- Run [31604919850](https://github.com/MahmoudAlZougbhi/linasbot-server/actions/runs/31604919850) **failed**: `granular_targets_allowlisted`
- This validates **repo GitHub Actions secrets** (`META_PAGE_ACCESS_TOKEN`), **not** the live encrypted registry used by production readiness.
- **Do not** disconnect/reconnect/rotate live Meta tokens for this. Optional later: owner may refresh the **GHA secret** to match allowlisted page/IG targets for CI hygiene only.

### Verdict

**VERIFIED** for production VERIFY_AND_PRESERVE. No OTP/login stop required for the checks above.

---

## C. Production preflight + rollback (prepare only)

### Current production

| Item | Value |
|------|-------|
| Host | `ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01` (`139.59.167.62`) |
| Deployed SHA | `781a94ca3d50b02b6a8da1b0afeaeaa32e01bb26` |
| Subject | Merge pull request #238 (`feat/wa-app-review-temp-bind`) |
| `origin/main` on host | same SHA |
| Rollback SHA for this release | **`781a94ca3d50b02b6a8da1b0afeaeaa32e01bb26`** (redeploy previous) |
| Rollback procedure | On host: `cd /opt/linasbot && git fetch origin && git reset --hard 781a94ca3d50b02b6a8da1b0afeaeaa32e01bb26 && sudo bash /opt/linasbot/deploy.sh` |
| New release SHA | merge commit of PR #240 (after owner merge approval) |

### Migration state (expected)

- Single Alembic head on branch: **`20260812_customer_requests`**
- Parent: `20260811_wa_app_review_source` (shipped with deployed #238)
- Prod Requests tables: **not created yet** (Phase 13 apply still owner-gated)
- WA Cloud Postgres reachable (`wa-probe` SUCCESS; `LINAS_WHATSAPP_DATABASE_URL` scheme `postgresql+psycopg2`)

### Postgres backup command (prepare; do not run until owner approval)

On production host with env loaded (never log URI/password):

```bash
# After owner approval — example pattern (adjust OUT dir; do not commit dumps)
set -a; source /opt/linasbot/.env; set +a
SNAP_DIR=/opt/linasbot_backups/pg/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$SNAP_DIR"
# Use URI from LINAS_WHATSAPP_DATABASE_URL (psql/pg_dump compatible form)
pg_dump --format=custom --file="$SNAP_DIR/linas_wa_cloud.dump" "$PGDUMP_URI"
echo "$SNAP_DIR" > /opt/linasbot_backups/pg/LATEST_SNAPSHOT_PATH
```

Restore plan: `pg_restore --clean --if-exists -d "$PGDUMP_URI" "$SNAP_DIR/linas_wa_cloud.dump"` only after owner approval; prefer restore to a scratch DB first.

### Firestore backup / rollback

- Live Chat / dashboard users remain in Firestore project wired via `/opt/linasbot/data/firebase_data.json`
- Preflight: Firestore OK; dashboard_users present; `live_chat_index` dry-run exit 0
- Indexes: repo `firestore.indexes.json` — **no automatic deploy**; owner activates per `docs/FIRESTORE_INDEXES_DEPLOY.md` only if composite-index errors appear
- Rollback of app code does not wipe Firestore; avoid destructive collection deletes

### nginx (read-only)

- Unique vhost: `/etc/nginx/sites-enabled/linasaibot` → `sites-available/linasaibot`
- `nginx -t` OK
- Webhook challenge SUCCESS (meta + WA)
- Repo source of truth: `deploy/nginx-linasaibot.conf` + `deploy/nginx-api-include.conf` (`location ^~ /webhook`)
- Local SSH unavailable → full live↔repo unified diff not captured byte-for-byte; **functional verification READY**. Do **not** reload nginx in Phase 13.

### systemd (read-only)

- Unit: `/etc/systemd/system/linasbot.service`
- EnvironmentFile: `/opt/linasbot/.env` (mode `0600`)
- MainPID present; service serving `/api/ready`
- Worker template in repo: `deploy/systemd/linasbot-worker@.service` (optional queues; not required for Redis purchase gate)
- Do **not** daemon-reload / restart as part of Phase 13 prep

### Prod env checklist (names only — present on host)

Required security present per preflight: `ENVIRONMENT=production`, `DASHBOARD_AUTH_SECRET`, `OPENAI_API_KEY`, `MONTYMOBILE_API_KEY`, Meta App A / page / IG / webhook verify token set, firebase file present.  
Still needed before Redis-backed rate limits: reachable `RATE_LIMIT_REDIS_URL` / `REDIS_URL`.  
Do **not** set `LINASLASER_BOC_BOOKING_ENABLED=true`.

### PR #240 CI

- Origin tip checked green: backend / frontend / mobile / secret-scan / deploy-readiness **SUCCESS** on head `768ebe7…`
- Freeze app SHA remains `9757d01…`
- Docs-only tip may advance after this report commit; reconfirm CI on tip before merge

---

## D. Requests migration `20260812_customer_requests`

| Topic | Finding |
|-------|---------|
| Nature | **Additive** `CREATE TABLE` only for Requests domain; no ALTER/DROP of WA Cloud tables |
| Lock / rewrite risk | Low — new empty tables + indexes; transactional DDL on Postgres |
| Downtime risk | Minimal (seconds of migration transaction); no table rewrite |
| Backward compat with current deploy (`781a94c`) | **Safe** — deployed code does not require Requests tables; empty tables idle until #240 serves Requests APIs |
| Single head | **Yes** — `20260812_customer_requests` |
| Validation | Ephemeral Postgres 16: `alembic upgrade head` → tables present; `downgrade` to parent drops only Requests tables; re-upgrade OK |
| Prod apply | **NOT DONE** — requires backup + explicit Mahmoud approval |

### Prepared sequence (owner-approved only)

1. Postgres custom dump (section C)
2. `alembic current` → expect `20260811_wa_app_review_source`
3. `bash scripts/prod_whatsapp_cloud_migrate.sh` **or** `alembic upgrade head` with prod URL (script upgrades to head — will apply Requests revision once code containing it is on disk; if migrating **before** merge, install revision file then upgrade)
4. Verify: `\dt customer_request*` + `alembic current` = `20260812_customer_requests`
5. Rollback if needed: `alembic downgrade 20260811_wa_app_review_source` (drops Requests tables only) **or** restore dump

**Recommended cutover order:** backup → apply migration → merge #240 / deploy.

---

## E. Remaining owner actions (execution order)

1. **Approve Redis purchase** — Valkey `linas-redis-prod`, **lon1**, `db-s-1vcpu-1gb`, ~**$15/mo** (UI or doctl above).  
2. After cluster online: approve firewall + wire `RATE_LIMIT_REDIS_URL`/`REDIS_URL` (TLS/auth); multi-worker smoke; **do not** enable `LINAS_REQUIRE_REDIS` unless separately approved.  
3. **Meta:** no OTP required for VERIFY_AND_PRESERVE. Optional: fix GHA `META_PAGE_ACCESS_TOKEN` allowlist mismatch for CI-only Token Validate workflow — **without** touching live Meta connection.  
4. **Approve Postgres backup**, then **approve apply** of `20260812_customer_requests` on production.  
5. **Approve merge** of PR #240 → Quality Gates → Production Deploy.  
6. Phase 15 live smoke after deploy.

---

## Evidence links

| Item | Link / path |
|------|-------------|
| Prod Preflight Readonly | https://github.com/MahmoudAlZougbhi/linasbot-server/actions/runs/31604899975 |
| Meta App A Scope Audit | https://github.com/MahmoudAlZougbhi/linasbot-server/actions/runs/31604922810 |
| Meta Comment Runtime Probe | https://github.com/MahmoudAlZougbhi/linasbot-server/actions/runs/31604926038 |
| Meta Social Token Validate (GHA secrets fail) | https://github.com/MahmoudAlZougbhi/linasbot-server/actions/runs/31604919850 |
| WA Cloud Webhook Readonly Probe | https://github.com/MahmoudAlZougbhi/linasbot-server/actions/runs/31605188815 |
| Rate limit Redis docs | `docs/RATE_LIMIT_REDIS.md` |
| Firestore index deploy gate | `docs/FIRESTORE_INDEXES_DEPLOY.md` |

---

**Phase 13 status:** Prep work complete for everything inspectable without paid purchase / prod mutation. Overall release still **NOT_READY** until owner clears Redis purchase, migration apply approval, and merge approval.
