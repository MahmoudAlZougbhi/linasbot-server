# Linas AI — Firebase vs mobile auth audit

## Verdict on the “Firebase gate”

**The mobile beta does not embed Firebase Auth and does not need a client Firebase config file for login.**

Earlier “Login needs Firebase…” wording mixed two different things:

1. **Local Mac API process** — server startup uses Firebase Admin (`data/firebase_data.json` / `FIRESTORE_SERVICE_ACCOUNT_KEY_PATH`) to talk to Firestore. That file is **missing on this Mac**, so a *local* API is hard to run here.
2. **Distributed TestFlight/APK** — talks to **HTTPS** `https://linasaibot.com`. Login is email/password → `POST /api/auth/mobile/login` → server `user_service.authenticate` (Firestore via **server-side** Firebase Admin). **No Firebase SDK in `mobile/linas-ai`.**

Production `/api/ready` already reports `firestore.ok: true`, so the **server already has** Linas Firebase Admin credentials. Do **not** create a second Firebase project. Do **not** copy SportBook/BOC credentials.

## Mobile-safe client configuration (OK to ship)

| Item | Status |
|------|--------|
| `EXPO_PUBLIC_API_BASE_URL` / `extra.apiBaseUrl` | `https://linasaibot.com` |
| Bundle / package id | `com.linasai.app` |
| App display name, icons, splash | Configured |
| SecureStore for access/refresh tokens | Used |
| Microphone permission string (voice→STT via **backend**) | Configured |

**Not required for this beta login path:**

- `GoogleService-Info.plist`
- `google-services.json`
- Firebase Web API key / Auth domain in the app
- Any Firebase client SDK

## Server-only credentials (NEVER in the app)

| Item | Role |
|------|------|
| Firebase/Firestore **service account JSON** (`firebase_data.json` / `FIRESTORE_SERVICE_ACCOUNT_KEY_PATH`) | Admin SDK on API host |
| `DASHBOARD_AUTH_SECRET` / session signing | Access tokens |
| OpenAI / Meta / Stripe / Redis URLs with passwords | Provider & infra |
| Private keys (`.p8`, Apple keys, etc.) | Signing / store |

Never print or commit these.

## Actual login blocker (not Firebase client)

Live probe:

```text
POST https://linasaibot.com/api/auth/mobile/login
→ 401 {"success":false,"error":"Authentication required"}
```

That response is the **generic auth middleware** because Phase 2 public routes (`/api/auth/mobile/login`, `/api/auth/mobile/refresh`, owner-ai, mobile STT, …) are **not deployed** on production yet (still on PR #97). Firestore itself is healthy on prod.

**Fix:** deploy Phase 2 API code to production **without** enabling `LINAS_REQUIRE_REDIS` (Redis/workers not required for login/chat/CM/usage). Keep `CM_DISABLE_LINAS_LEGACY_BRIDGE=true`.

## Manual Firebase Console?

**Not required** for this beta, as long as production continues using the existing Linas Firebase/Firestore project (already wired server-side).

Only if Mahmoud later wants **native Firebase Auth / Analytics / Crashlytics** would we register iOS/Android apps in Firebase Console for `com.linasai.app` and add **client** config files. That is out of scope for this email/password bearer beta.
