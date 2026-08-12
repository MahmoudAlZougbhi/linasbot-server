# Google Sign-In wiring (existing OAuth clients)

**Status:** `GOOGLE_LOGIN_READY=yes` (config + backend verify live; device E2E on new store builds)  
**Date:** 2026-08-13  
**Branch:** `fix/google-oauth-native-clients`

## Clients (do not recreate)

| Kind | Client ID | Notes |
|------|-----------|--------|
| Web | `513717053157-bqn6moo5q15q4c54bnmcgct07hrn8e1g.apps.googleusercontent.com` | Expo `clientId` / ID-token request |
| Android | `513717053157-gegscca3fjh5e3qthacbs5k5a7gelrhn.apps.googleusercontent.com` | Package `com.linasai.app`; SHA-1 `D7:26:3F:43:75:01:06:1F:58:6F:F7:3C:E6:79:4A:B3:E6:7B:9E:3D` |
| iOS | `513717053157-sp9fa5fqpg2f7pj5evbtkeucon1v4mm1.apps.googleusercontent.com` | Bundle `com.linasai.app`; reverse scheme in `app.json` |

## Mobile

- EAS env (production / testflight / preview): `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`, `EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID`, `EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID`
- Flow: `expo-auth-session` `useIdTokenAuthRequest` → `POST /api/auth/mobile/google`
- Duplicate email → `409 link_required`; logout clears mobile tokens via existing `/api/auth/mobile/logout`

## Backend

- `GOOGLE_OAUTH_CLIENT_IDS` on **both** nodes = Web,iOS,Android (comma-separated audiences)
- Verifies RS256 + Google JWKS; issuer `accounts.google.com`; aud/exp/sub; `email_verified`
- **No** `GOOGLE_OAUTH_CLIENT_SECRET` required for this ID-token path (secret must never ship in mobile/git)

## Forbidden honored

- No new OAuth clients
- No BOC enable
- No Requests migration
- No secret values printed

## EAS builds (this wiring)

| Platform | Build ID | Profile | Version |
|----------|----------|---------|---------|
| iOS TestFlight | `6a89dd01-1141-47a8-a341-129ef4939187` | testflight | 1.0.0 (44) |
| Android AAB | `edad34e3-cb12-420e-9e74-0d367e55e880` | production | 1.0.0 (vc26) |

- iOS logs: https://expo.dev/accounts/mahmoudalzoughbi/projects/linas-ai/builds/6a89dd01-1141-47a8-a341-129ef4939187
- Android logs: https://expo.dev/accounts/mahmoudalzoughbi/projects/linas-ai/builds/edad34e3-cb12-420e-9e74-0d367e55e880
- Play Internal auto-submit: **blocked** — no Google Play service-account JSON on this machine / in EAS submit credentials. Upload AAB manually after build finishes (Play Console → Testing → Internal testing).

## Store delivery

| Item | Status |
|------|--------|
| iOS TestFlight submit | Scheduled `a26a2fde-1617-40ad-a10d-883fa920d761` |
| iOS IPA | https://expo.dev/artifacts/eas/aCI-YanM13cvIrMPHjkJ-haXJJDzlfMEUzR_APen0R0.ipa |
| Android AAB | https://expo.dev/artifacts/eas/lm4502TaEf2DMJBtY1SP0SHgN2zD25OehGj2hwybguY.aab |
| Local AAB | `artifacts/mobile/linas-ai-v1.0.0-vc26-google-native.aab` |
| Play Internal auto-upload | **BLOCKED** — EAS lacks Google Play service-account (non-interactive setup refused). Manual: Play Console → Testing → Internal testing → Upload AAB |

## Verification checklist

- [x] Backend audiences Web+iOS+Android on both nodes; restart active
- [x] Bad token → 401 (LB + local nodes)
- [x] Unit tests `tests/test_google_sign_in.py` (4 passed)
- [x] No client secret in mobile / git / nodes
- [ ] Owner device: Android native Google login + iOS Google login on builds above

