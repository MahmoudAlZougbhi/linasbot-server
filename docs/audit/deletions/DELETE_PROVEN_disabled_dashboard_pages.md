# DELETE_PROVEN: product-disabled unmounted dashboard pages

**Status:** PROVEN UNUSED — deleted  
**Date:** 2026-08-12  
**Branch:** chore/project-cleanup-reorg

## Scope

Frontend page modules that are product-disabled and **not mounted** in `App.jsx` (routes redirect away). Backend smart_messaging / meta social-posts APIs are **out of scope** and kept.

## Deleted units

| Path | Former route | App.jsx behavior |
|---|---|---|
| `dashboard/src/pages/SmartMessaging.jsx` | `/smart-messaging` | `<Navigate to="/content-managers" replace />` |
| `dashboard/src/pages/SmartMessaging.approval.test.jsx` | (test only) | Imports only `SmartMessaging` |
| `dashboard/src/pages/Testing.jsx` | `/testing` | `<Navigate to="/content-managers" replace />` |
| `dashboard/src/pages/Testing.social.test.jsx` | (test only) | Imports only `Testing` + `testingLabSession` |
| `dashboard/src/utils/testingLabSession.js` | — | Imported only by `Testing.jsx` / Testing tests |
| `dashboard/src/utils/testingLabSession.test.js` | — | Tests only `testingLabSession` |
| `dashboard/src/pages/SocialPostCreator.jsx` | `/social-posts` | `<Navigate to="/content-managers" replace />` |
| `dashboard/src/pages/SimpleApiTest.jsx` | `/api-debug` | `<Navigate to="/content-managers" replace />` |

## Checks performed

| Check | Result |
|---|---|
| `App.jsx` lazy imports / `<Route element={<…}>` for these pages | **None** — redirects only |
| `rg` imports of `SmartMessaging` / `Testing` / `SocialPostCreator` / `SimpleApiTest` under `dashboard/src` | Only self + co-located page tests (deleted with pages) |
| `productFeatures.js` `DISABLED_FRONTEND_ROUTES` | Lists `/testing`, `/api-debug`, `/smart-messaging`, `/social-posts` |
| `Sidebar.jsx` | Comment: Testing Lab / Smart Messaging / Create Post remain disabled/hidden; product surface test asserts Testing Lab link absent |
| `testingLabSession*` consumers | Only `Testing.jsx` + `Testing.social.test.jsx` + own unit test |
| `useApi.getSmartMessagingTemplates` | **Kept** — still used by `LiveChat.jsx` |
| `services/smart_messaging*` / smart-messaging API | **Not deleted** (explicit out of scope) |
| `Analytics.jsx` | **Not deleted** — see `BLOCKED_Analytics_dashboard_home.md` (`Dashboard.jsx` renders it as `/app` home) |

## App.jsx / useApi cleanup

- `App.jsx`: no dead page imports to remove (pages were already unimported; redirect routes retained as product-disable surface).
- `useApi.jsx`: no safe dead-import removal for these pages (`getSmartMessagingTemplates` remains Live Chat–owned).

## Tests run

```text
cd dashboard && npm test -- src/App.routes.test.jsx src/publicLanding.test.jsx src/pages/Analytics.test.jsx src/components/Layout/Sidebar.productSurface.test.jsx
```

## Action

`git rm` the deleted units listed above; add this evidence doc + `BLOCKED_Analytics_dashboard_home.md`.
