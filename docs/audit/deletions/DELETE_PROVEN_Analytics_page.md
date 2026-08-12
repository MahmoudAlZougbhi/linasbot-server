# DELETE_PROVEN: dashboard Analytics page

## Former purpose
Operator Analytics dashboard UI; also mounted as `/app` via `Dashboard.jsx`.

## Why removed
- Product route `/analytics` already redirected away (`productFeatures` / App.jsx).
- `/api/analytics` already disabled.
- `/app` home rewritten to a simple SaaS link hub (no Analytics dependency).
- LiveChat no longer calls disabled smart-messaging templates API (related cleanup in same change).

## Checks performed
- static imports of `Analytics.jsx` after Dashboard rewrite
- App.jsx routes (`/app` → Dashboard, `/analytics` → Navigate)
- productFeatures DISABLED_FRONTEND_ROUTES includes `/analytics`

## Replacement
- `/app`: `Dashboard.jsx` link hub to SAAS_NAV_ITEMS
- Analytics API writers (`services/analytics_events.py`) kept for chat/usage — not this page

## Tests
- Prior disabled-page vitest batch green; this change removes Analytics.test.jsx with the page
