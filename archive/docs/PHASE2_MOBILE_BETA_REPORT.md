# Linas AI Mobile Beta Report

## Verdict

**NOT LINAS AI MOBILE BETA READY — BLOCKERS: Phase 2 backend not deployed to production HTTPS; Expo/EAS account login; Apple Developer / App Store Connect for TestFlight**

Installable Android APK was produced and installed on a physical device. Login against `https://linasaibot.com` cannot succeed until PR #97 mobile APIs are live.

---

## Audit

| Item | Value |
|------|-------|
| Expo SDK | ~57.0.11 |
| React Native | 0.86.2 |
| App name | Linas AI |
| Slug | linas-ai |
| iOS bundle id | `com.linasai.app` |
| Android package | `com.linasai.app` |
| Version | 1.0.0 |
| iOS buildNumber | 1 |
| Android versionCode | 1 |
| API environment | `https://linasaibot.com` (HTTPS) |
| EAS projectId | `replace-after-eas-init` (needs Expo login) |
| Profiles | development / preview / production in `eas.json` |

## Branding

- Regenerated app icon + splash from existing Linas mark (`android-icon-foreground.png`).
- Construction-grid placeholders removed.
- No new logo invented.

## Android APK (local preview)

| Item | Value |
|------|-------|
| Profile intent | `preview` (APK) |
| EAS build ID | **N/A — Expo account not logged in** |
| Artifact | `mobile/linas-ai/dist/linas-ai-preview-1.0.0.apk` (local; gitignored) |
| Also at | `mobile/linas-ai/android/app/build/outputs/apk/release/app-release.apk` |
| versionName / versionCode | 1.0.0 / 1 |
| Signing | Android Debug (device-installable beta; not Play upload key) |
| Device install | Success on USB device `RFCTA1V6PGH` (`com.linasai.app` running) |

This is **not** a Play Store `.aab`.

## iOS / TestFlight

| Item | Status |
|------|--------|
| Bundle id | `com.linasai.app` |
| Expo iOS export | OK |
| EAS iOS build | Blocked — Expo login |
| TestFlight submit | Blocked — Apple Developer + App Store Connect |

### Exact Apple / Expo interaction gate (Mahmoud)

1. On this Mac: `cd mobile/linas-ai && npx eas-cli login` (Expo account).
2. `npx eas-cli init` → accept linking project; copy real `projectId` into `app.json` `extra.eas.projectId`.
3. `npx eas-cli credentials -p ios` → log into Apple Developer when prompted (2FA).
4. Create App Store Connect app with bundle id `com.linasai.app` if missing.
5. `npx eas-cli build -p ios --profile preview` (or `production` for TestFlight binary).
6. When build finishes: `npx eas-cli submit -p ios --latest` → TestFlight only (do **not** submit for App Store Review).
7. Add internal testers in App Store Connect → TestFlight.

Do not paste Apple passwords into chat.

## Backend environment

| Check | Result |
|-------|--------|
| HTTPS | `https://linasaibot.com` OK |
| `/api/auth/mobile/login` | **Not live** (middleware 401 — Phase 2 not deployed) |
| Owner chat / CM / usage / integrations / STT | On feature branch; need deploy |

**Ask Mahmoud:** approve production deploy of PR #97 so the beta APK can authenticate. Do not alter Meta assets.

## Simulator / emulator

| Surface | Result |
|---------|--------|
| Android physical device | APK installed + process started |
| Android emulator login E2E | Blocked on API (same as device) |
| iOS Simulator full E2E | Bundle export OK; native run/TestFlight blocked on Apple/EAS; login blocked on API |
| Bundle secret scan | Clean (no OpenAI/Meta/server secrets) |

## Known beta limitations

- IAP purchases not provisioned (`purchase_ready=false`)
- Meta comments/publish not `live_verified`
- TikTok/Snap coming later
- Video generation disabled in Creative Studio UI
- Release APK uses debug signing (fine for sideload beta)

## PR / CI

Push this beta commit on `feat/linas-ai-phase2-app-first` / PR #97.
