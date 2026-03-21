/**
 * Base URL for API calls (no trailing slash).
 * - REACT_APP_API_URL when set (e.g. CDN frontend + API on another host).
 * - Else in the browser we pick a safe default so Smart Messaging `fetch(apiUrl(...))` does not 404:
 *   - Port 3000/3001: same-origin `""` so `/api` goes through `setupProxy.js` (npm start).
 *   - Port 8003/8080 on localhost: same-origin `""` (FastAPI or similar serves SPA + API).
 *   - Any other localhost port (e.g. `serve -s build` on 5000): `http://localhost:8003` because
 *     there is no dev proxy and relative `/api` would hit the static server and return 404.
 * - Else (production / LAN hostname): same-origin `""` (expect nginx or same host to proxy `/api/`).
 */
export const getApiBaseUrl = () => {
  const env = (process.env.REACT_APP_API_URL || "").trim().replace(/\/$/, "");
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
