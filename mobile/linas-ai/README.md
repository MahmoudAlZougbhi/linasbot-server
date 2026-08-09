# Linas AI Mobile (Expo)

Production-oriented iOS + Android client for Linas AI.

## Stack

- Expo SDK 57 + React Native
- TypeScript strict
- Secure token storage (`expo-secure-store`)
- Zod-validated API responses

## Configure

Set `EXPO_PUBLIC_API_BASE_URL` to your Linas API origin (default `https://linasaibot.com`).

## Commands

```bash
npm install
npm run typecheck
npm start
npm run ios
npm run android
```

## Product surfaces

- Home = Linas AI chat
- Control Center = CM, Create, Integrations, Usage, Subscription, Users, Scheduled, Settings
- Owner Control Center (platform_owner only)

Do not copy SportBook code into this app.
