const isLocalDevHost = () =>
  typeof window !== "undefined" &&
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");

export const getApiBaseUrl = () => {
  const envUrl = typeof process !== "undefined" && process.env?.REACT_APP_API_BASE_URL;
  if (envUrl && String(envUrl).trim()) return String(envUrl).trim().replace(/\/$/, "");
  if (isLocalDevHost()) return "http://localhost:8003";
  return "";
};

// Use relative URL in dev so proxy forwards /api to backend; full origin in production
export const getApiAbsoluteBaseUrl = () => {
  const base = getApiBaseUrl();
  if (base) return base;
  return typeof window !== "undefined" ? window.location.origin : "";
};
