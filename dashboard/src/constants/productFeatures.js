/**
 * Frontend mirror of services/product_features.py — Wave 1 disabled product surface.
 * Keep in sync when adding/removing disabled modules.
 */

export const DISABLED_FRONTEND_ROUTES = [
  "/testing",
  "/api-debug",
  "/live-chat",
  "/mobile/live-chat",
  "/smart-messaging",
  "/activity-flow",
  "/social-posts",
  "/analytics",
];

/** Active SaaS navigation (Content Management + settings/wallet). */
export const SAAS_NAV_ITEMS = [
  { name: "Dashboard", href: "/app", permissionKey: "dashboard" },
  { name: "Content Managers", href: "/content-managers", permissionKey: "contentManagers" },
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
