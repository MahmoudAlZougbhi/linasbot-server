const isLocalDevHost = () =>
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

export const getApiBaseUrl = () => (isLocalDevHost() ? "http://localhost:8003" : "");

export const getApiAbsoluteBaseUrl = () =>
  isLocalDevHost() ? "http://localhost:8003" : window.location.origin;
