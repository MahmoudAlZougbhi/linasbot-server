export const PLATFORM_PORTAL_HOSTS = new Set([
  'portal.linasaibot.com',
  'www.portal.linasaibot.com',
]);

/** @param {string} [hostname] */
export function isPlatformPortalHost(hostname) {
  const host = String(
    hostname ?? (typeof window !== 'undefined' ? window.location.hostname : ''),
  )
    .trim()
    .toLowerCase();
  return PLATFORM_PORTAL_HOSTS.has(host);
}
