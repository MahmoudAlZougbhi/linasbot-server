# FINAL PRODUCTION LIVE REPORT

**Verdict:** `PRODUCTION_LIVE_AND_TEST_BUILDS_READY`  
**Generated:** 2026-08-12T21:50:00Z  
**Operator:** Autonomous release execution (PR #240 + follow-on Google Sign-In #242)

---

## Production identity

| Field | Value |
|-------|--------|
| Production SHA (both nodes) | `1932249679bd6e8c6c4343d43c36767f150b9247` |
| PR #240 merge SHA | `12e61810fcdb0e508a278f144388a60d38902bc5` |
| FINAL_RC_SHA (mobile freeze tip) | `b3f428475325860a2252e6a0cf33776d7e81c4ea` |
| PREVIOUS_PROD_SHA (rollback) | `7ed5c3fd5068191a5a0b20e64a85fbb9fb43d076` |
| PG backup (pre-merge) | `/opt/linasbot_backups/pg/20260812T211314Z` on node01 |
| LB | `linas-http-lb-lon1` `157.245.31.104` active |
| Managed PG | `linas-postgres-prod` online (2 nodes) |
| Managed Valkey | `linas-redis-prod` online (2 nodes); `LINAS_REQUIRE_REDIS=false` |

---

## Services status (post-cutover smoke)

| Check | Result |
|-------|--------|
| `https://linasaibot.com/api/health` | 200 / ok |
| `https://linasaibot.com/api/ready` | ok=true |
| BOC | **OFF** (`enabled: false`) |
| Meta messaging / registry | ready; `registry_backend_ready: true` |
| Redis job queue | configured + reachable; **not** required/fail-closed |
| Apple ASSN endpoints | POST empty → **400** (live, rejects bad payload) |
| Google auth endpoint | POST bad token → **401** (live) |
| Billing/auth/meta SoT | **Postgres defaults** (file pins removed after import+parity) |
| Alembic on Managed PG | `20260812_apple_billing` only (Requests/outbox **not** applied) |
| node01 / node02 app SHA | both `1932249…` |
| BOC / Requests migration / droplet resize / NFS delete | **not done** (forbidden) |

---

## Mobile builds

### iOS TestFlight

| Field | Value |
|-------|--------|
| EAS build ID | `f5f08009-2457-4e59-ac27-ec9ad1722d8f` |
| Version / build | `1.0.0` / **43** |
| Commit | `9a8528aff3f4e116a4740e7a690c86765a5f13f9` (Google Sign-In + SIWA profile fix) |
| Submit | **Uploaded to App Store Connect** — submission `7f85bb9e-c07a-479a-bf52-c13a1a7aacad` |
| TestFlight URL | https://appstoreconnect.apple.com/apps/6799678918/testflight/ios |
| IPA artifact | https://expo.dev/artifacts/eas/SOy6OCLNOO-Udra2ojqXgkOyJcqotLDO0NDavKU7id8.ipa |

Note: first RC iOS attempt `bee0c9a6-…` failed (provisioning profile missing Sign in with Apple). Regenerated profile `VFA236JFGH` and rebuilt successfully.

### Android Internal Testing AAB

| Field | Value |
|-------|--------|
| EAS build ID (RC AAB) | `c4827c0a-fc04-4ada-b24c-226f606fba84` |
| Version / versionCode | `1.0.0` / **24** |
| Commit | `b3f428475325860a2252e6a0cf33776d7e81c4ea` (FINAL_RC_SHA) |
| Local path | `artifacts/mobile/linas-ai-v1.0.0-vc24.aab` (~69 MB) |
| Artifact URL | https://expo.dev/artifacts/eas/fHYmhWdhxJ9b99y7UD3kTPNR3kal4Zk5p3vEwSNnj4k.aab |
| Play Internal upload | **BLOCKED_OWNER_ACTION** — EAS lacks Google Play service-account key (non-interactive setup refused) |
| Native-client AAB (iOS+Android IDs) | EAS build `edad34e3-cb12-420e-9e74-0d367e55e880` versionCode **26** |
| Native-client iOS TF | EAS build `6a89dd01-1141-47a8-a341-129ef4939187` build **44** |

---

## Auth / billing status

| Surface | Status |
|---------|--------|
| Email / password mobile auth | Live (PG token backend) |
| Apple Sign In | Code + TestFlight build ready; ASC ASSN URL registration still owner UI |
| Google Sign-In | **Wired** — Web+iOS+Android client IDs in EAS + `GOOGLE_OAUTH_CLIENT_IDS` on both nodes (no client secret required for ID-token verify); package `com.linasai.app`; Android SHA-1 `D7:26:3F:43:75:01:06:1F:58:6F:F7:3C:E6:79:4A:B3:E6:7B:9E:3D` |
| Billing SoT | Postgres after import+parity; wallets/refresh/email tokens/credits matched |
| Stripe / Apple IAP / Google Play RTDN | Code ready; Play products/RTDN still owner console |

---

## Remaining BLOCKED_OWNER_ACTION (exact click paths)

### 1) Google Cloud — iOS + Android OAuth clients

**DONE (existing clients wired; no new clients created).**

| Platform | Client ID (public) |
|----------|--------------------|
| Web | `513717053157-bqn6moo5q15q4c54bnmcgct07hrn8e1g.apps.googleusercontent.com` |
| Android | `513717053157-gegscca3fjh5e3qthacbs5k5a7gelrhn.apps.googleusercontent.com` |
| iOS | `513717053157-sp9fa5fqpg2f7pj5evbtkeucon1v4mm1.apps.googleusercontent.com` |

- Mobile: `EXPO_PUBLIC_GOOGLE_{WEB,IOS,ANDROID}_CLIENT_ID` in EAS production/testflight/preview  
- Backend both nodes: `GOOGLE_OAUTH_CLIENT_IDS` = Web,iOS,Android (comma-separated); client secret **absent** (not required)  
- iOS reverse scheme registered in `app.json` schemes  

### 2) Google Play — Internal Testing upload + API access

1. https://play.google.com/console → app **Linas AI** (`com.linasai.app`)  
2. **Testing → Internal testing → Create release → Upload AAB**  
   Local file: `artifacts/mobile/linas-ai-v1.0.0-vc24.aab`  
3. For EAS submit automation: **Setup → API access →** link service account JSON into EAS Android submit credentials  
4. Create subscription products + RTDN (runbook §10) when ready for billing tests.

### 3) Apple App Store Connect — ASSN + Sandbox

1. My Apps → **Linas AI** → **App Store Server Notifications → Version 2**  
   - Production URL: `https://linasaibot.com/webhooks/apple/app-store`  
   - Alias also live: `/api/webhooks/apple/app-store`, `/api/entitlements/apple/notifications`  
2. Send **TEST** notification.  
3. Confirm Apple `.p8` paths on both nodes (`0600`) per runbook §9.  
4. Higher Price Point for Pro/Scale Yearly (owner ASC).

### 4) Post-soak (not this window)

- Enable `LINAS_REQUIRE_REDIS` / `LINAS_FAIL_CLOSED_REDIS_CLAIMS` only after soak GO  
- Requests Alembic past Apple — separate GO  
- Droplet resize / NFS removal — prepare-only

---

## Forbidden honored

- No BOC enable  
- No Requests/outbox migration  
- No droplet delete / NFS delete  
- No Meta reconnect/rebuild (VERIFY_AND_PRESERVE)  
- No Redis require/fail-closed enable  
- No secret values printed

---

## Owner test prep (Phase 6)

Ready for owner device tests once TestFlight processing finishes (~5–10 min) and Android Internal AAB is uploaded manually:

- Account: email login + Apple SIWA (TestFlight)  
- Google: native iOS/Android clients wired; test Google button on new TestFlight + Internal AAB after processing  
- AI / Content / Social / Meta: production ready checks green  
- Requests: code on servers; **DB migration not applied** (expected)  
- Billing: PG SoT live; store purchase matrices need ASC/Play external steps  

---

## Rollback

```bash
PREVIOUS_PROD_SHA=7ed5c3fd5068191a5a0b20e64a85fbb9fb43d076
# per node: git reset --hard "$PREVIOUS_PROD_SHA" && sudo bash /opt/linasbot/deploy.sh
# emergency SoT: LINAS_BILLING_BACKEND=file LINAS_AUTH_TOKEN_BACKEND=file META_REGISTRY_BACKEND=file
```
