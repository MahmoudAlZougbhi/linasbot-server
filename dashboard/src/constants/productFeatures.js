/**
 * Frontend mirror of services/product_features.py — disabled product surface.
 * Keep in sync when adding/removing disabled modules.
 * Live Chat + Interaction Logs are enabled again.
 */

export const DISABLED_FRONTEND_ROUTES = [
  "/testing",
  "/api-debug",
  "/smart-messaging",
  "/social-posts",
  "/analytics",
];

/** Primary SaaS navigation (plus Live Chat / Interaction Logs in Sidebar). */
export const SAAS_NAV_ITEMS = [
  { name: "Dashboard", href: "/app", permissionKey: "dashboard" },
  { name: "AI Setup", href: "/content-managers", permissionKey: "contentManagers" },
  { name: "Interaction Logs", href: "/activity-flow", permissionKey: "activityFlow" },
  { name: "Live Chat", href: "/live-chat", permissionKey: "liveChat" },
  { name: "Settings", href: "/settings", permissionKey: "settings" },
  { name: "Token Wallet", href: "/wallet", permissionKey: "settings" },
];

/**
 * @param {string} pathname
 * @returns {boolean}
 */
export function isDisabledFrontendRoute(pathname) {
  if (!pathname) return false;
  const p = pathname.length > 1 && pathname.endsWith("/") ? pathname.replace(/\/+$/, "") : pathname;
  return DISABLED_FRONTEND_ROUTES.some((route) => p === route || p.startsWith(`${route}/`));
}
