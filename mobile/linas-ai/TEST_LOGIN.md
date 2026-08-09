# Linas AI — test login (no secrets)

Mobile login uses the same dashboard users via:

`POST /api/auth/mobile/login` → Bearer access + refresh tokens

## After Phase 2 API is on https://linasaibot.com

1. Open the Linas AI app (TestFlight / preview APK).
2. Use your **existing dashboard account email + password** (the same credentials you use at `/login` on the website).
3. If login returns “API not ready”, the mobile auth routes are not deployed yet — merge/deploy `feat/linas-ai-phase2-app-first` (or main containing Phase 2 mobile auth) first.

## Local / demo without printing production secrets

1. Ensure a local server runs with mobile auth modules loaded.
2. Register via the app **Create account** screen (`/api/auth/register`) or the website register page.
3. Verify email if your environment requires it.
4. Log in with that email/password in the app.

Do **not** invent Firebase client config. Google/Apple buttons are UI-only (“Coming soon”) until backend OAuth is wired.

## Bundle / EAS identifiers (must not change)

- iOS / Android: `com.linasai.app`
- EAS projectId: `d15fe78a-09df-4d7c-81a5-2b307956fddf`
- Profile: `testflight` in `eas.json`
