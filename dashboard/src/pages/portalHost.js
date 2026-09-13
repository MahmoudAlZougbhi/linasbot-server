export const PLATFORM_PORTAL_HOSTS = new Set([
  'portal.linasaibot.com',
  'www.portal.linasaibot.com',
]);

export const MARKETING_PUBLIC_HOSTS = new Set(['linasaibot.com', 'www.linasaibot.com']);

/** @param {string} [hostname] */
function currentHostname(hostname) {
  return String(
    hostname ?? (typeof window !== 'undefined' ? window.location.hostname : ''),
  )
    .trim()
    .toLowerCase();
}

/** @param {string} [hostname] */
export function isPlatformPortalHost(hostname) {
  return PLATFORM_PORTAL_HOSTS.has(currentHostname(hostname));
}

/** Marketing site: no web login, no owner portal. Team uses the mobile app.
 * @param {string} [hostname] */
export function isMarketingPublicHost(hostname) {
  return MARKETING_PUBLIC_HOSTS.has(currentHostname(hostname));
}
