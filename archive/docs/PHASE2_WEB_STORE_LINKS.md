# Public web store links (marketing landing)

Public marketing badges read `STORE_LINKS` in `dashboard/src/constants/publicSite.js`.

| Store | Package / bundle | Status | URL in repo |
|-------|------------------|--------|-------------|
| Apple App Store | `com.linasai.app` | **pending** | No public `apps.apple.com/app/id…` URL or numeric ASC Apple ID committed yet (TestFlight / ASC gate). |
| Google Play | `com.linasai.app` | **pending** | Listing not live; do not invent a Play URL. |

When a listing goes live:

1. Set `STORE_LINKS.appStore.status = 'live'` and `url` to the real App Store URL.
2. Set `STORE_LINKS.playStore.status = 'live'` and `url` to `https://play.google.com/store/apps/details?id=com.linasai.app` (or the console URL).
3. Badges on `/` will become real outbound links automatically.

Until then, badges render as **Coming soon** (truthful, non-clickable).
