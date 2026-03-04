const isLocalDevHost = () =>
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

export const getApiBaseUrl = () => (isLocalDevHost() ? "http://localhost:8003" : "");

// Use relative URL in dev so proxy forwards /api to backend; full origin in production
export const getApiAbsoluteBaseUrl = () =>
  isLocalDevHost() ? "" : window.location.origin;
