# Linas AI (Expo)

Installable beta app for Linas AI. Privileged AI/provider calls go through the Linas HTTPS API only.

## Identifiers

- Display name: **Linas AI**
- Bundle / package: `com.linasai.app`
- Version: `1.0.0` (iOS buildNumber `1`, Android versionCode `1`)

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
- `production` — future store (AAB / App Store)

Requires Expo login + `eas init` to replace `extra.eas.projectId`.

## Local Android preview APK

```bash
export JAVA_HOME=...
export ANDROID_HOME=...
cd android
EXPO_PUBLIC_API_BASE_URL=https://linasaibot.com EXPO_PUBLIC_APP_ENV=preview ./gradlew assembleRelease
# output: app/build/outputs/apk/release/app-release.apk
```
