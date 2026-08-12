# Linas AI Mobile Beta — status

**Verdict: NOT LINAS AI MOBILE BETA READY — BLOCKERS: (1) Expo/EAS login (2) Deploy Phase 2 mobile API to https://linasaibot.com (3) Apple credentials after Expo login for TestFlight upload**

## Firebase / mobile auth

See `docs/PHASE2_FIREBASE_MOBILE_AUTH_AUDIT.md`.

- Client Firebase: **not needed** for current login.
- Server Firebase Admin: **already on production** (`firestore.ok`).
- Missing for beta UX: **Phase 2 mobile auth routes on the HTTPS host**.

## Beta API

| Env | URL | Mobile login |
|-----|-----|--------------|
| Production (preferred) | `https://linasaibot.com` | **Blocked** until PR #97 deploy |
| Localhost | n/a for TestFlight/APK | Do not use |

Redis workers: **not** required to unlock login/chat/CM/usage. Keep `LINAS_REQUIRE_REDIS` unset until separately activated. Preserve `CM_DISABLE_LINAS_LEGACY_BRIDGE=true`.

## Builds

| Artifact | Status |
|----------|--------|
| Android APK | Local preview at `mobile/linas-ai/dist/linas-ai-preview-1.0.0.apk` (package `com.linasai.app`, 1.0.0 / versionCode 1). EAS cloud APK blocked on Expo login. |
| iOS TestFlight | Blocked on Expo login → EAS store build → submit |

## Identifiers

- iOS: `com.linasai.app`
- Android: `com.linasai.app`
- Version: `1.0.0` / iOS build `1` / Android versionCode `1`

## Exact Mahmoud actions (in order)

### A) Expo login (blocks EAS + TestFlight)

```bash
cd /Users/alzoughbi/linasbot-server/mobile/linas-ai
npx eas-cli login
npx eas-cli whoami
```

Then reply: **Expo logged in — continue TestFlight**

### B) Approve production deploy of PR #97 (blocks real-device login)

Approve merge + normal production deploy of https://github.com/MahmoudAlZougbhi/linasbot-server/pull/97  
(or explicit: “Deploy Phase 2 API to production without Redis hard-require”).

Do **not** set `LINAS_REQUIRE_REDIS=true` in that deploy unless Redis is ready.

### C) After Expo login — Apple 2FA when EAS asks

Allow EAS to manage App Store distribution cert + profile for `com.linasai.app`.  
Provide numeric App Store Connect **Apple ID** for the Linas AI app if submit cannot auto-detect.

### D) Not required now

- New Firebase project
- Client `GoogleService-Info.plist` / `google-services.json`
- IAP products, Meta comments Advanced Access, public App Store Review, Play production
