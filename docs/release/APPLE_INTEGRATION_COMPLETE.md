# Apple Auth + StoreKit + IAP + Subscriptions — Integration Report

**Branch:** `chore/project-cleanup-reorg`  
**Head SHA:** `988900f40c2d162d84a106e82622d0a75a2c9956`  
**CI:** backend · frontend · mobile · secret-scan · deploy-readiness = **pass** (no merge to main; no deploy)  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Rules honored:** no merge to main · no production deploy · BOC off · Meta unchanged · no `.p8` committed

---

## Verdict

| Code | Status |
|------|--------|
| **APPLE_CODE_READY_FOR_STORE_REVIEW** | **YES** for repository/code completeness (auth, StoreKit 2 client, ASSN V2, ledger, credits, refunds, REFUND_REVERSED restore, CONSUMPTION_REQUEST, tests, secrets wiring prepared) |
| **BLOCKED_EXTERNAL_REVIEW** | **YES** — Pro Yearly + Scale Yearly require Apple Higher Price Point approval before those two SKUs can go live at intended prices |
| **BLOCKED_OWNER_ACTION** | **YES** — App Store Connect notification URL registration, Sandbox interactive runs on device/TestFlight, production secret deploy (authorized separately), Higher Price Point form submit |

Do **not** treat notification URLs as live until Mahmoud registers them in App Store Connect.

---

## Configuration (locked)

| Item | Value |
|------|--------|
| Bundle ID | `com.linasai.app` |
| Team ID | `55624L5UXL` |
| Sign in Key ID | `5FK9G38WRJ` |
| Sign in key path (local) | `~/.linasai-secrets/apple/AuthKey_5FK9G38WRJ.p8` (mode 0600; **not** in git) |
| IAP Issuer | `a3b052c7-c0ed-4935-8e2e-4b57946e1f6b` |
| IAP Key ID | `8H9SZG552B` |
| IAP key path (local) | `~/.linasai-secrets/apple/SubscriptionKey_8H9SZG552B.p8` (mode 0600; **not** in git) |
| Subscription group | Linas AI Subscriptions / `22305050` |

Local `.p8` files verified present (paths/sizes only — private key material never logged).

---

## Product mapping (ASC → Linas plan_id)

| ASC product prefix | Linas plan |
|--------------------|------------|
| `com.linasai.subscription.basic.*` | `lite` |
| `com.linasai.subscription.plus.*` | `starter` |
| `com.linasai.subscription.growth.*` | `growth` |
| `com.linasai.subscription.pro.*` | `pro` |
| `com.linasai.subscription.scale.*` | `max` |

Credits (server-owned quantities): `com.linasai.credits.{2500,5000,12500,25000,50000}`.

UI prices: StoreKit `displayPrice` only — no hardcoded checkout USD.

---

## What shipped

### Sign in with Apple
- Mobile: `expo-apple-authentication` + raw nonce (Expo hashes; server compares SHA-256)
- Server: JWKS verify (`aud=com.linasai.app`, iss, exp, sub)
- PG `auth_external_identities` — `provider+sub` uniqueness; no email-only merge
- Private relay treated as normal email; no forced verification challenge
- Link / unlink / self-service account delete
- Rate limits on `POST /api/auth/mobile/apple`

### StoreKit 2 (mobile)
- `react-native-iap` dependency (autolink on native prebuild/EAS; **not** listed as Expo config plugin)
- Verify-before-`finishTransaction`
- Monthly/Yearly toggle, credit packs, restore, manage subscriptions, refund request sheet
- Stable `appAccountToken` UUID from server

### Server billing authority
- App Store Server API client (prod → sandbox lookup per Apple docs)
- ASSN V2: `POST /webhooks/apple/app-store`, `POST /api/webhooks/apple/app-store`, alias `POST /api/entitlements/apple/notifications`
- PG ledger: `apple_transactions`, `apple_notification_events`, `apple_credit_grants`, `apple_app_account_tokens`
- Idempotent subscription + consumable grants; refund reverse-once; **REFUND_REVERSED** restores credits/subscription
- **CONSUMPTION_REQUEST** → `send_consumption_info` when IAP credentials configured (fail-soft)
- Client verify requires matching `appAccountToken` (no free cross-tenant bind)
- Missed-notification reconcile CLI: `scripts/apple_notification_reconcile.py`
- Migrations: `alembic/versions/20260812_credit_entitlements_pg.py`, `20260812_apple_billing.py` (Apple chained **before** Requests)

### HA entitlements / credits (code; flags default file)
- `LINAS_BILLING_BACKEND=postgres` covers credit ledger + tenant entitlements + processed-event idempotency (plus wallets/Stripe/admin)
- Do **not** flip on production without import + soak approval

### Security fixes
- Client verify requires `appAccountToken`
- First Apple registration uses token email only (no client-email squat)
- Nonce SHA-256 contract aligned with Expo
- Apple auth rate limits
- Ledger refuses tenant rebind

---

## Notification URL handoff (owner ASC UI)

Register **after** deploy of this code to an HTTPS host (not done in this task):

| Env | Exact URL |
|-----|-----------|
| Production | `https://linasaibot.com/webhooks/apple/app-store` |
| Production (alias) | `https://linasaibot.com/api/webhooks/apple/app-store` |
| Production (legacy alias) | `https://linasaibot.com/api/entitlements/apple/notifications` |
| Sandbox | Same paths (Apple Sandbox URL field — same host with Sandbox environment selected in ASC) |

**Click path:** My Apps → Linas AI → App Store Server Notifications → Version 2 → Save → send TEST notification.

---

## Higher Price Point — text for Mahmoud

1. **In-app refund request:** StoreKit refund request sheet from billing UI.
2. **ASSN V2:** Implemented with JWS verification + idempotent renewals/expirations/refunds/revokes/REFUND_REVERSED/CONSUMPTION_REQUEST.
3. **Refund / cancellation processing:** Reverse-once credits; REFUND_REVERSED restores; duplicates no-op.
4. **Support / risk:** `appAccountToken` binding; server verify; PG transaction ledger; rate-limited SIWA; `support@linasaibot.com`.

After approval, configure **Pro Yearly** and **Scale Yearly** in ASC. Do **not** substitute lower fake yearly prices.

---

## Sandbox status

| Area | Automated | Interactive device Sandbox |
|------|-----------|----------------------------|
| Apple JWT verify / link / nonce | Pass (offline JWKS mocks) | Needs device + Sandbox Apple ID |
| IAP idempotency / refund / cross-tenant | Pass (mocked JWS) | Needs StoreKit Sandbox |
| ASSN V2 signature path | Fail-closed + unit processing | Needs ASC TEST after URL register |
| Expo Go IAP | N/A | **Blocked** — use dev client / TestFlight |

---

## Secret wiring (prepared — not deployed)

```
APPLE_TEAM_ID=55624L5UXL
APPLE_BUNDLE_ID=com.linasai.app
APPLE_SIGN_IN_KEY_ID=5FK9G38WRJ
APPLE_SIGN_IN_PRIVATE_KEY_PATH=<protected 0600 path>
APPLE_IAP_ISSUER_ID=a3b052c7-c0ed-4935-8e2e-4b57946e1f6b
APPLE_IAP_KEY_ID=8H9SZG552B
APPLE_IAP_PRIVATE_KEY_PATH=<protected 0600 path>
```

---

## OWNER_ACTIONS remaining

1. Register ASSN V2 Production + Sandbox URLs in App Store Connect; send TEST notification
2. Deploy secrets to HA app nodes when release is authorized (not now)
3. Run interactive Sandbox matrix on TestFlight/dev client
4. Submit Higher Price Point request; then price Pro/Scale yearly
5. Capture App Review screenshots from real purchase UI
6. Apply Alembic through `20260812_apple_billing` on Managed PG when infra cutover approved (Requests still owner-gated separately)

---

## Residual HA note

Apple transaction/identity/credit-grant tables are Postgres SoT. Credit ledger + entitlements are **PG-capable** under `LINAS_BILLING_BACKEND=postgres` (default remains `file` until cutover). Do not flip billing/auth/registry flags on production without approval.
