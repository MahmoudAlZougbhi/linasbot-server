# Linas AI — TestFlight upload gate (Mahmoud)

**Verified:** `ios.bundleIdentifier` = `com.linasai.app` (unchanged)  
**App version:** `1.0.0`  
**iOS buildNumber:** `1`  
**Commit to build:** current `feat/linas-ai-phase2-app-first` HEAD  
**Blocked:** Expo/EAS CLI is **not logged in** on this machine (`eas whoami` → Not logged in). No `EXPO_TOKEN` in environment.

TestFlight requires an EAS **store** distribution iOS build (`testflight` / `production` profile), then `eas submit`. This is **not** App Store Review.

## Exact steps for Mahmoud (do these in Terminal)

### 1) Expo login (required first)

```bash
cd /Users/alzoughbi/linasbot-server/mobile/linas-ai
npx eas-cli login
```

- Browser opens (or use `npx eas-cli login --no-browser` for email/password in CLI).
- Complete Expo account login / 2FA if prompted.
- Confirm: `npx eas-cli whoami` prints your Expo username.

**Optional (for CI/agents):** create an Expo access token at https://expo.dev/settings/access-tokens and set:

```bash
export EXPO_TOKEN='your_token'
```

Then tell the agent to continue (do not paste the token into chat).

### 2) Link EAS project (one-time)

```bash
cd /Users/alzoughbi/linasbot-server/mobile/linas-ai
npx eas-cli init
```

- Choose your Expo account / org.
- Accept creating/linking project for slug `linas-ai`.
- This replaces `extra.eas.projectId` in `app.json` (currently `replace-after-eas-init`).
- Commit the updated `app.json` projectId.

### 3) Apple credentials for store signing

```bash
npx eas-cli credentials -p ios
```

When prompted:

1. Select the `com.linasai.app` app.
2. Log into **Apple Developer** (Apple ID + **2FA**).
3. Allow EAS to manage distribution certificate + App Store provisioning profile for `com.linasai.app`
   (or select existing ones if you already created them).

### 4) App Store Connect App ID (numeric)

In App Store Connect → **Linas AI** → App Information, copy the numeric **Apple ID** (not the bundle id).

Edit `eas.json` → `submit.testflight.ios.ascAppId` (and `submit.production`) to that number  
**or** pass it on submit: `--id <NUMERIC_ASC_APP_ID>`.

### 5) After login succeeds — tell the agent “continue TestFlight”

The agent will run (non-interactive where possible):

```bash
cd /Users/alzoughbi/linasbot-server/mobile/linas-ai
npx eas-cli build -p ios --profile testflight --non-interactive
npx eas-cli submit -p ios --profile testflight --latest --non-interactive
```

- **Will** upload to App Store Connect / TestFlight.
- **Will not** submit for public App Store Review.

### 6) After processing

In App Store Connect → TestFlight:

- Wait for Apple processing (often 5–30+ minutes).
- Answer any **Export Compliance** / encryption question if asked (app sets `ITSAppUsesNonExemptEncryption=false`).
- Add yourself as internal tester if needed.
- Confirm build appears under TestFlight (status leaves “No Builds”).

## What is already ready

- Bundle ID `com.linasai.app`
- App name Linas AI
- `eas.json` profiles: `testflight` / `production` use `distribution: store`
- Microphone permission string + encryption flag for App Store metadata
- Beta app code on branch / PR #97
