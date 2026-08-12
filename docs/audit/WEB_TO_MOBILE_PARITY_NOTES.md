# Web → Mobile parity notes (APPROVED #7)

**Matrix:** `docs/audit/FINAL_WEB_TO_MOBILE_PARITY_MATRIX.csv`  
**Evidence basis:** `dashboard/src/App.jsx` routes + `mobile/linas-ai/src/app/AppScreenTree.tsx` / `drawerModules.ts` / `cmSections.ts` (2026-08-12).

## Trim gate

Operator SPA may leave the web shell when each operator row is **PARITY**, **PARTIAL** (mobile primary), or **DEFERRED_OWNER** with an explicit reason. This matrix meets that bar.

## Keep on web (landing-only)

- Marketing: `/`, `/about`, `/contact`, `/pricing`, `/features`
- Thin auth: `/login`, `/forgot-password`, `/reset-password`, `/verify-email`
- Guest chat on landing (`GuestChatPanel`)
- Public legal URLs (`/privacy-policy`, `/terms`, `/data-deletion`) via site/footer
- `/mobile/live-chat` APK/WebView bridge (Expo `LiveChatScreen` is primary; APK download still linked from Sidebar asset)

## Deferred / partial gaps (honest)

| Gap | Status | Reason |
|---|---|---|
| Learning Inbox | DEFERRED_OWNER | No mobile screen; LiveChat like→FAQ only partial |
| Sources & Archive | DEFERRED_OWNER | Ops inventory; not day-to-day mobile |
| Activity Flow / Interaction Logs | DEFERRED_OWNER | No mobile screen (permission key only) |
| Token Wallet Stripe packs | PARTIAL vs Billing | Mobile Billing = plans/credits; no wallet checkout found |
| CM Publish hub page | PARTIAL | Chat/`publish_cm` + CM readiness CTA |
| Creative Studio | n/a | No CreativeStudio path on disk at matrix time; social-posts web route is redirect-only |

## Do not delete

- Mobile APIs / Expo screens
- Landing, legal, guest chat, thin auth routes
