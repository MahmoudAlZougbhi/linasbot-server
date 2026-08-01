/**
 * True if REACT_APP_API_URL points at loopback (browser would call the visitor's machine, not your server).
 * Production builds must not bake http://localhost:8003 — nginx proxies /api on the real domain.
 */
function isApiBaseLoopbackOnly(url) {
  if (!url || typeof url !== "string") return false;
  try {
    const normalized = url.includes("://") ? url : `http://${url}`;
    const u = new URL(normalized);
    const h = (u.hostname || "").toLowerCase();
    return (
      h === "localhost" ||
      h === "127.0.0.1" ||
      h === "[::1]" ||
      h === "0.0.0.0"
    );
  } catch {
    return /\blocalhost\b|127\.0\.0\.1/i.test(url);
  }
}

/**
 * Base URL for API calls (no trailing slash).
 * - REACT_APP_API_URL when set (e.g. CDN frontend + API on another host).
 * - If the site is opened on a real domain (e.g. linasaibot.com) but the build baked
 *   REACT_APP_API_URL=http://localhost:8003 (common docker-compose default), we ignore that
 *   env and use same-origin `/api/` so nginx can proxy — fixes Smart Messaging "Send test" HTTP 404.
 * - Else in the browser we pick a safe default:
 *   - Port 3000/3001: same-origin `""` (setupProxy / npm start).
 *   - Port 8003/8080 on localhost: same-origin `""`.
 *   - Other localhost ports: `http://localhost:8003` (static preview without proxy).
 * - Production / LAN hostname: same-origin `""` (nginx proxies `/api/`).
 */
export const getApiBaseUrl = () => {
  let env = (process.env.REACT_APP_API_URL || "").trim().replace(/\/$/, "");
  if (typeof window !== "undefined" && env) {
    const host = window.location.hostname;
    const onPublicSite =
      host &&
      host !== "localhost" &&
      host !== "127.0.0.1" &&
      host !== "[::1]";
    if (onPublicSite && isApiBaseLoopbackOnly(env)) {
      env = "";
    }
  }
  if (env) return env;
  if (typeof window === "undefined") return "";

  const { hostname, port } = window.location;
  const effectivePort =
    port ||
    (window.location.protocol === "https:" ? "443" : "80");

  const isLoopback =
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "[::1]";

  if (isLoopback) {
    if (effectivePort === "3000" || effectivePort === "3001") {
      return "";
    }
    if (effectivePort === "8003" || effectivePort === "8080") {
      return "";
    }
    return "http://localhost:8003";
  }

  return "";
};

/** Absolute or same-origin URL for an API path (must start with /). */
export const apiUrl = (path) => {
  const p = path.startsWith("/") ? path : `/${path}`;
  const base = getApiBaseUrl();
  return base ? `${base}${p}` : p;
};

const isLocalDevHost = () =>
  typeof window !== "undefined" &&
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");

/** Live chat / media: use relative URLs in dev (proxy), full origin in production. */
export const getApiAbsoluteBaseUrl = () =>
  isLocalDevHost() ? "" : window.location.origin;
