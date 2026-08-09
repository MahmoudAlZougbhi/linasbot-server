# Phase 2 — External App Store / Play checklist

Backend code for entitlements + store notification endpoints is prepared.
**`purchase_ready` remains false until sandbox verification succeeds with real credentials.**

Do **not** invent secrets. Create credentials only in Apple/Google consoles, then set server EnvironmentFile names from `.env.example`.

## Apple (App Store Connect)

1. Create App ID / bundle `com.linasai.app`.
2. Create auto-renewable subscriptions (monthly):
   - Starter **$24.99**
   - Growth **$59**
   - Pro **$109**
   - Max **$250**
3. Map product IDs into `LINAS_IAP_PRODUCT_MAP_JSON` on the server.
4. Configure App Store Server Notifications V2 →  
   `https://linasaibot.com/api/entitlements/apple/notifications`
5. Create App Store Connect API key (Issuer ID, Key ID, `.p8`) and set:
   - `APPLE_BUNDLE_ID`
   - `APPLE_APP_STORE_KEY_ID`
   - `APPLE_APP_STORE_ISSUER_ID`
   - `APPLE_APP_STORE_PRIVATE_KEY_PATH` (path on server; never commit key)
6. Sandbox purchase each SKU; confirm entitlement `active`, renewal, cancel/grace/refund paths via Owner Control Center + ledger.

## Google Play

1. Create Play app package `com.linasai.app`.
2. Create matching subscription products + base plans at the same prices.
3. Enable Play Developer API + Real-time developer notifications (Pub/Sub).
4. Create service account with Android Publisher access; place JSON on server and set:
   - `GOOGLE_PLAY_PACKAGE_NAME`
   - `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_PATH`
5. Bridge RTDN to  
   `https://linasaibot.com/api/entitlements/google/notifications`
6. License-tester purchase each SKU; confirm entitlement transitions.

## Until then

- Notification endpoints return **503** (fail closed) without credentials / verifier binding.
- Platform owner may inject verified sandbox events via `/api/entitlements/iap/manual-event` only after real external purchase evidence.
- Mobile store listing / TestFlight / internal testing tracks require Mahmoud’s Apple/Google developer accounts.
