/**
 * Read CSRF token from cookie `linas_csrf` or localStorage fallback `csrf_token`.
 */
export function getCsrfToken() {
  if (typeof document !== "undefined" && document.cookie) {
    const match = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("linas_csrf="));
    if (match) {
      return decodeURIComponent(match.slice("linas_csrf=".length));
    }
  }
  try {
    return localStorage.getItem("csrf_token") || "";
  } catch {
    return "";
  }
}

/** Headers object with X-CSRF-Token when a token is available. */
export function csrfHeaders() {
  const token = getCsrfToken();
  return token ? { "X-CSRF-Token": token } : {};
}
