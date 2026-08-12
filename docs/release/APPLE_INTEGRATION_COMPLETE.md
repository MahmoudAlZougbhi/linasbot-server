# Apple Auth + StoreKit + IAP + Subscriptions — Integration Report

**Branch:** `feat/apple-auth-billing` → merged into `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Rules honored:** no merge to main · no production deploy · BOC off · Meta unchanged · no `.p8` committed

---

## Verdict

| Code | Status |
|------|--------|
| **APPLE_CODE_READY_FOR_STORE_REVIEW** | **YES** for repository/code completeness (auth, StoreKit 2 client, ASSN V2, ledger, credits, refunds, tests, secrets wiring prepared) |
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

Local `.p8` files verified present (paths/sizes/PEM headers only — private key material never logged).

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
- `react-native-iap` dependency (autolink on native prebuild/EAS; **not** listed as Expo config plugin — package has no `app.plugin.js` and breaks `expo export`)
- Verify-before-`finishTransaction`
- Monthly/Yearly toggle, credit packs, restore, manage subscriptions, refund request sheet
- Stable `appAccountToken` UUID from server

### Server billing authority
- App Store Server API client (prod → sandbox lookup per Apple docs)
- ASSN V2: `POST /webhooks/apple/app-store`, `POST /api/webhooks/apple/app-store`, alias `POST /api/entitlements/apple/notifications`
- PG ledger: `apple_transactions`, `apple_notification_events`, `apple_credit_grants`, `apple_app_account_tokens`
- Idempotent subscription + consumable grants; refund reverse-once
- Client verify requires matching `appAccountToken` (no free cross-tenant bind)
- Missed-notification reconcile CLI: `scripts/apple_notification_reconcile.py`
- Migration: `alembic/versions/20260812_apple_billing.py`

### Security fixes applied in this branch
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
| Sandbox | Same paths (Apple sends Sandbox notifications to the Sandbox URL field — use the same host with Sandbox environment selected in ASC) |

**Click path (App Store Connect):**  
My Apps → Linas AI → App Information / App Store Server Notifications → edit Production + Sandbox URLs → Version 2 → Save → send TEST notification.

TLS: production site already serves HTTPS. TEST notification result: **not run** until URLs are registered and secrets are on the server (owner action).

---

## Higher Price Point — text for Mahmoud

Suggested truthful answers for Apple’s Higher Price Point request (do not submit unless you choose to):

1. **In-app refund request:** Implemented via StoreKit refund request sheet from the subscription/purchase management UI (`iapPurchases` / Billing screen). Users initiate refunds through Apple’s native flow — not a fake Linas form.
2. **App Store Server Notifications V2:** Implemented at `POST /webhooks/apple/app-store` with cryptographic JWS verification and idempotent processing for renewals, expirations, refunds, revokes, and related lifecycle events.
3. **Refund / cancellation processing:** Refund and revoke notifications reverse consumable credit grants once (ledger + entitlement extra credits) and update subscription entitlement status; duplicates are no-ops.
4. **Customer support / risk mitigation:** Account linking requires authenticated link; purchases bound via `appAccountToken`; server-side transaction verification; durable Postgres transaction ledger; rate-limited Apple sign-in; support reply-to `support@linasaibot.com`.

After approval, configure **Pro Yearly** and **Scale Yearly** price points in ASC. Do **not** substitute lower fake yearly prices in the app.

---

## Review materials (prepared, not submitted)

- First subscription + group + credit consumables: product IDs above
- Review Notes draft: “Sign in with Apple; subscriptions and credit packs via Apple IAP; prices from StoreKit; Sandbox tester required for purchase paths.”
- Screenshots: capture after TestFlight build with live StoreKit UI (not invented here)
- Rebuild required for mobile plugins (`usesAppleSignIn`, IAP native module)

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

Server env (both HA nodes when authorized):

```
APPLE_TEAM_ID=55624L5UXL
APPLE_BUNDLE_ID=com.linasai.app
APPLE_SIGN_IN_KEY_ID=5FK9G38WRJ
APPLE_SIGN_IN_PRIVATE_KEY_PATH=<protected 0600 path>
APPLE_IAP_ISSUER_ID=a3b052c7-c0ed-4935-8e2e-4b57946e1f6b
APPLE_IAP_KEY_ID=8H9SZG552B
APPLE_IAP_PRIVATE_KEY_PATH=<protected 0600 path>
```

Aliases `APPLE_APP_STORE_*` accepted. Never expose paths to mobile.

---

## Tests / gates

| Gate | Result |
|------|--------|
| `tests/test_apple_sign_in.py` + `tests/test_apple_iap_processor.py` | 17 collected; passing |
| Auth matrix + billing/membership related | Passing |
| Mobile `npm test` | 108 pass |
| Mobile typecheck / secret-scan | Pass |
| LOC policy (`check_source_line_limit`) | Pass (≤400 checked roots; Apple modules ≤500) |
| Ruff (Apple modules) | Pass |
| `.p8` tracked | None |
| Mobile private keys | None |

---

## OWNER_ACTIONS remaining

1. Register ASSN V2 Production + Sandbox URLs in App Store Connect; send TEST notification  
2. Deploy secrets to HA app nodes when release is authorized (not now)  
3. Run interactive Sandbox matrix on TestFlight/dev client  
4. Submit Higher Price Point request (optional now); then price Pro/Scale yearly  
5. Capture App Review screenshots from real purchase UI  
6. Apply Alembic `20260812_apple_billing` on Managed PG when infra cutover approved  

---

## Residual HA note

Apple transaction/identity/credit-grant tables are Postgres SoT. Existing `entitlements_store` / `credit_ledger` file residual still used for entitlement application effects until the broader billing PG cutover — Apple ledger/idempotency does **not** reintroduce file-backed transaction SoT. Do not flip `LINAS_BILLING_BACKEND=postgres` without separate approval.
