const isLocalDevHost = () =>
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

/**
 * Base URL for API calls (no trailing slash).
 * - REACT_APP_API_URL when set at build time (e.g. frontend on CDN, API on another host).
 * - Else on localhost/127.0.0.1: direct backend default port (bypasses CRA proxy when needed).
 * - Else empty: same-origin relative paths (e.g. nginx → backend in Docker).
 */
export const getApiBaseUrl = () => {
  const env = (process.env.REACT_APP_API_URL || "").trim().replace(/\/$/, "");
  if (env) return env;
  if (isLocalDevHost()) return "http://localhost:8003";
  return "";
};

/** Absolute or same-origin URL for an API path (must start with /). */
export const apiUrl = (path) => {
  const p = path.startsWith("/") ? path : `/${path}`;
  const base = getApiBaseUrl();
  return base ? `${base}${p}` : p;
};

/** Live chat / media: use relative URLs in dev (proxy), full origin in production. */
export const getApiAbsoluteBaseUrl = () =>
  isLocalDevHost() ? "" : window.location.origin;
