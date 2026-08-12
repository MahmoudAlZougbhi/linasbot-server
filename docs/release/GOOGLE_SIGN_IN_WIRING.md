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
