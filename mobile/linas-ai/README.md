# Linas AI (Expo)

Installable beta app for Linas AI. Privileged AI/provider calls go through the Linas HTTPS API only.

## Identifiers

- Display name: **Linas AI**
- Bundle / package: `com.linasai.app`
- EAS project: `d15fe78a-09df-4d7c-81a5-2b307956fddf`
- App Store Connect: `6799678918`
- Marketing version: `1.0.0` (`expo.version` — bump manually only for user-facing releases)
- Developer build: iOS `buildNumber` / Android `versionCode` (auto-bumped; see Versioning)

## Versioning

Store / TestFlight identity that must be unique each ship is the **build number**, not the marketing version.

| Field | Source of truth | Who bumps it |
| --- | --- | --- |
| `expo.version` (`1.0.0`) | `app.json` | Manual, only for product releases |
| iOS `buildNumber` | EAS **remote** | `autoIncrement` on `production` / `testflight` |
| Android `versionCode` | EAS **remote** | same |

`eas.json` sets `cli.appVersionSource` to `remote` and `autoIncrement: true` on `production` and `testflight`. That way each EAS ship gets a new build without committing `app.json`. Local `app.json` values are a seed / fallback for non-store profiles; remote wins for TF/store builds.

In-app label (NavDrawer + Settings) reads live from `expo-constants` via `APP_VERSION_LABEL` / `APP_BUILD_LABEL` in `src/config.ts`, e.g. `Linas 1.0.0 · 20`. After install, open the side menu or Settings — the build segment must match the new native build.

If App Store Connect / Play already has a higher build than EAS remote remembers, sync once before the next ship:

```bash
cd mobile/linas-ai
eas build:version:set -p ios
eas build:version:set -p android
```

## Server update gate

Marketing version checks use server env (not build numbers):

| Env | Purpose |
| --- | --- |
| `MOBILE_APP_LATEST_VERSION` | Newest semver shown to clients (`1.0.1`, …) |
| `MOBILE_APP_MIN_SUPPORTED_VERSION` | Below this → `force_update` |
| `MOBILE_APP_IOS_STORE_URL` | Optional App Store link |
| `MOBILE_APP_ANDROID_STORE_URL` | Optional Play Store link |

Public API:

- `GET /api/public/app-version` — config
- `POST /api/public/app-version/check` — body `{ "installed_version": "1.0.0" }` → `up_to_date` \| `update_available` \| `force_update`

On cold start the app calls check with `expo.version` only. iOS `buildNumber` / Android `versionCode` stay separate (EAS remote `autoIncrement`).

## Config

```bash
# Public only — never put provider/server secrets here
EXPO_PUBLIC_API_BASE_URL=https://linasaibot.com
EXPO_PUBLIC_APP_ENV=preview
```

## Checks

```bash
npm ci
npm run prebuild:check
npm run secret-scan
```

## EAS profiles

See `eas.json`:

- `development` — dev client / debug
- `preview` — internal installable **APK** + iOS internal build
- `testflight` — App Store distribution for TestFlight (`autoIncrement`, ASC `6799678918`)
- `production` — store (AAB / App Store; `autoIncrement`)

Project id is already set in `app.json` → `extra.eas.projectId`.

## Local Android preview APK

```bash
export JAVA_HOME=...
export ANDROID_HOME=...
cd android
EXPO_PUBLIC_API_BASE_URL=https://linasaibot.com EXPO_PUBLIC_APP_ENV=preview ./gradlew assembleRelease
# output: app/build/outputs/apk/release/app-release.apk
```
