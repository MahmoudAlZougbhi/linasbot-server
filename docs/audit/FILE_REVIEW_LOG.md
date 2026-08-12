# Phase 0B — File Review Log

Audit-only. Application source is not modified.

## Progress

| Metric | Value |
|--------|-------|
| Tracked files (`git ls-files`) | 1539 |
| Inventory rows | 1539 |
| COMPLETE | 205 |
| UNREVIEWED | 1334 |
| IN_REVIEW | 0 |
| Last batch | Batch 7 (seq 176–205) |
| Last audit commit | `0497d78` |

---

## Batch 1 — seq 1–25 (2026-08-12)

### Files opened and fully read

1. `.dockerignore`
2. `.env.example`
3. `.github/workflows/cm-linas-content-audit.yml`
4. `.github/workflows/cm-production-cutover.yml`
5. `.github/workflows/copilot-v2-flags-apply.yml`
6. `.github/workflows/dashboard-auth-secret-apply.yml`
7. `.github/workflows/deploy.yml`
8. `.github/workflows/instagram-login-secrets-apply.yml`
9. `.github/workflows/meta-app-a-login-config-apply.yml`
10. `.github/workflows/meta-app-a-scope-audit.yml`
11. `.github/workflows/meta-app-webhooks-reconcile.yml`
12. `.github/workflows/meta-comment-runtime-probe.yml`
13. `.github/workflows/meta-comment-webhooks-reconcile.yml`
14. `.github/workflows/meta-multi-app-secrets-apply.yml`
15. `.github/workflows/meta-page-subscription-subscribe.yml`
16. `.github/workflows/meta-social-atomic-cutover.yml`
17. `.github/workflows/meta-social-rollback-restore.yml`
18. `.github/workflows/meta-social-rollback-snapshot.yml`
19. `.github/workflows/meta-social-secrets-apply.yml`
20. `.github/workflows/meta-social-token-validate.yml`
21. `.github/workflows/meta-webhook-nginx-setup.yml`
22. `.github/workflows/model-routing-policy-apply.yml`
23. `.github/workflows/openai-api-key-apply.yml`
24. `.github/workflows/prod-preflight-readonly.yml`
25. `.github/workflows/quality-gates.yml`

### Findings summary

**Security**

- Seq 6, 8, 21, 23: secret/token apply workflows lack typed confirmation strings (unlike siblings).
- Seq 7: deploy uses older `appleboy/ssh-action@v1.0.3`; `/tmp` data backup window during `git reset --hard`.
- Seq 2: public WhatsApp E.164 contact numbers documented (expected); Monty/BOC placeholders still first-class.

**Correctness**

- Seq 10, 12: hardcode checkout from `fix/ig-fb-comments-capability-gates` (brittle).
- Seq 22: model-routing apply does not always refresh script from `origin/main` when file already exists.

**Performance**

- Seq 13: full `requirements.txt` install for thin reconcile script.
- Seq 25: heavy CI (expected).

**Legacy / product**

- Seq 2: mixed Meta Cloud + Monty template.
- Seq 24: probes still know `linaslaserbot-2.7.22` layout.
- Seq 25: still builds dashboard SPA.

**Deeper dependency tracing needed**

- All `scripts/prod_*` / `scripts/reconcile_*` / `scripts/validate_meta_*` / `scripts/manage_meta_*` / `deploy.sh` (canonical review when those sequence numbers are reached).

### Cumulative

COMPLETE **25 / 1539**

---

## Batch 2 — seq 26–55 (2026-08-12)

### Files opened and fully read

26–30 remaining WA/security workflows; 31 `.gitignore`; 32–38 `.planning/codebase/*`; 39 `PERSISTENT_STORAGE_REFACTOR.md`; 40 `README-LOCAL.md`; 41–46 alembic; 47 `api_config.py`; 48–51 backend Docker/requirements; 52 `config.py`; 53 `config/montymobile_templates.json`; 54–55 dashboard Docker.

### Findings summary

**Security**
- Seq 27: CI logs entitlement raw + exempt env values + all Firestore user display rows.
- Seq 30: `git reset --hard origin/main` on production during Phase1 apply.
- Seq 53: Monty `api_id`/`tenant`/source phone committed in JSON.

**Correctness**
- Seq 29: hardcoded 2026-08-11 probe windows; soft `exit 0`.
- Seq 40: `.env.local.example` vs `.env.example` mismatch.
- Seq 50: Docker health on :8000 vs project :8003.
- Seq 52: Welcome copy still Marwa/Lina Laser; import-time asset load.

**Legacy / product**
- Seq 32–38: MOVE_TO_ARCHIVE (Jan 2026 stale planning; claims no CI/tests).
- Seq 53: DELETE_CANDIDATE (Monty templates) pending caller cutover evidence.

### Cumulative

COMPLETE **55 / 1539**

---

## Batch 3 — seq 56–85 (2026-08-12)

### Files opened and fully read

- Text/config: `dashboard/Dockerfile.prod`, `README.md`, e2e specs, eslint, index.html, jsconfig, nginx, package.json, playwright, postcss, both landing SVGs
- Inspected (not source-read): `package-lock.json` (GENERATED_SKIP); PNG/JPG landing assets via metadata + `landingDesignAssets.js` refs

### Findings

- Seq 57 README MOVE_TO_ARCHIVE (tradershubs.site, port 8001, stale features)
- Seq 59/61/68–85 LANDING_KEEP
- Seq 64 GENERATED_SKIP

### Cumulative

COMPLETE **85 / 1539**

---

## Batch 4 — seq 86–115 (2026-08-12)

### Files opened / reviewed

- Brand PNGs 86–93 via metadata + `linasBrand.js` refs (NOT_APPLICABLE)
- Fully read: manifest, App.jsx, auth/tests, BotInstructionsTab, ErrorBoundary, LoadingScreen, ContentFilesPanel, DynamicMessagesPanel, Feedback/Like modals, Header, Sidebar(+tests), LiveChat mobile panes/helpers

### Key findings

- App `/mobile/live-chat` missing `requiredPermission="liveChat"` → KEEP_SECURITY_FIX
- Sidebar default `tenantId||"linas"` → KEEP_FIX
- Header fake notifications → KEEP_FIX
- BotInstructionsTab / ContentFilesPanel / DynamicMessagesPanel → DELETE_CANDIDATE (zero imports)

### Cumulative

COMPLETE **115 / 1539**

---

## Batch 5 — seq 116–145 (2026-08-12)

### Scope

Mobile LiveChat view/audio, orphaned TrainingFileEditor cluster, UserManagement, public landing sections + design assets.

### Highlights

- DELETE_CANDIDATE orphans: SystemPromptKnowledgeStylePanel, TrainingFileEditor*, LinasBotMascot (zero page imports)
- KEEP_SECURITY_FIX: RoleManager custom roles localStorage-only
- LANDING_KEEP: Hero/sections/GuestChat/header/footer
- KEEP_FIX: ModernAudioPlayer play-state; unused landing asset keys

### Cumulative

COMPLETE **145 / 1539**

---

## Follow-up — reconcile agent forensics (batches 3–5)

Applied sharper dispositions from completed audit agents without changing COMPLETE count:

- Seq 56 `Dockerfile.prod` → **KEEP_FIX** (Node 20 vs engines ≥22.19)
- Seq 77–85 design JPGs → **BINARY_ASSET_REVIEW**
- Seq 86–93 brand PNGs → **BINARY_ASSET_REVIEW** (`linasBrand.js` unused)
- Seq 96 App.routes.test → **KEEP_FIX** (does not import App)
- Seq 125 PermissionMatrix → **KEEP_FIX** (double-toggle)
- Confirmed seq 118/119/126/131 findings already aligned

Sources: agent audits for seq 56–85, 86–115, 116–145.

---

## Batch 6 — seq 146–175 (2026-08-12)

### Scope

Dashboard constants (brand/permissions/product/public), AuthContext cluster, Operator/Permissions/PublicLanding contexts, useApi* + Live Chat SSE/media hooks, index bootstrap, ActivityFlow page.

### Highlights

- **DELETE_CANDIDATE:** `linasBrand.js` (zero imports), `hooks/usePermissions.jsx` (duplicate of PermissionsContext)
- **KEEP_SECURITY_FIX:** `AuthContext.helpers` default `role=admin` / `tenantId=linas`; `AuthContext.jsx` session fail-open + auth console logs; `useLiveChatMediaComposer` hardcodes `operator_001`
- **KEEP_FIX:** `productFeatures` disable helper unused; `OperatorStatusContext` silent fallback; `useApiTesting` offline `success:true` mocks
- **LANDING_KEEP:** publicSite / publicLandingLocale / PublicLandingLocaleContext
- Active: permissions map, AuthProvider, useApi facade, Live Chat SSE, ActivityFlow `/activity-flow`

### Cumulative

COMPLETE **175 / 1539**

---

## Batch 7 — seq 176–205 (2026-08-12)

### Scope

ActivityFlow cluster, ContentManagers hub, Dashboard, auth pages, Live Chat page split (helpers→thread), Settings, Training redirect, VerifyEmail.

### Highlights

- **KEEP_SECURITY_FIX:** LiveChatSidebar exposes `simulateWebhook` (“Test flow”) + rebuild index; Settings `(tenantId||linas)` unlocks general/notifications
- **KEEP_FIX:** Dashboard nav tiles ignore permissions; LiveChatDetails stub Transfer/Priority; Login hardcodes personal `/Users/mahmoudalzougbhi/...` paths
- **KEEP_SPLIT:** LiveChatBotOverlay/Modals/ThreadHeader god-object prop dumps
- Active: Live Chat, AI Setup hub, Interaction Logs cards, Settings trimmed surface, Training→FAQ redirect

### Cumulative

COMPLETE **205 / 1539**

---

## Follow-up — reconcile agent forensics (batch 7)

Merged sharper notes from completed agents (seq 176–205) into inventory without changing COMPLETE count:

- Seq 189/191/194 → **KEEP_FIX** (unused-import / fragment debt)
- Seq 197 MobileLiveChat → **KEEP_SECURITY_FIX** (route missing `requiredPermission=liveChat`)
- Seq 203 Settings: keep **KEEP_SECURITY_FIX** tenantId default; append unused loaded-state fields
- Confirmed 190 stub buttons, 192 simulateWebhook, 196 Login paths already aligned

Sources: agent audits for seq 176–205 (duplicate agent runs).

---

## Follow-up — reconcile agent forensics (batch 6)

Merged sharper notes from completed agent (seq 146–175) without changing COMPLETE count:

- Seq 158 PermissionsContext → **KEEP_FIX** (`usePermissions` unused)
- Seq 160 useApi → **KEEP_PERFORMANCE_FIX** (full facade for botStatus-only App use)
- Seq 165 useApiQA → **KEEP_FIX** (dead QA exports; keep submitFeedback)
- Kept stronger **KEEP_SECURITY_FIX** on Auth helpers defaults + `operator_001` media composer

Source: agent audit for seq 146–175.
