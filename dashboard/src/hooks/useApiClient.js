import axios from "axios";
import toast from "react-hot-toast";
import { getApiBaseUrl } from "../utils/apiBaseUrl";
import { getCsrfToken } from "../utils/csrf";
import {
  errorMessage,
  getAxiosErrorCode,
  getAxiosResponseDetail,
  isAxiosLikeError,
  isPlainObject,
} from "../utils/apiValidate";

/** @param {string} message */
const toastInfo = (message) => {
  toast(message, { icon: "ℹ️" });
};

// Create axios instance with default config
const api = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 90000, // 90 seconds - increased for slow GPT responses
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor — refresh base URL each call (fixes stale baseURL if env/hostname logic changes)
api.interceptors.request.use(
  (config) => {
    config.baseURL = getApiBaseUrl();
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      config.headers["X-CSRF-Token"] = csrfToken;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    const code = isAxiosLikeError(error) ? error.code : undefined;
    // Handle network errors gracefully (silent)
    if (code === "ERR_NETWORK") {
      // Silent - no console logs for network errors
      if (process.env.NODE_ENV === "development") {
        return Promise.reject(error);
      }
    }

    // Handle timeout errors gracefully (silent)
    if (code === "ECONNABORTED") {
      // Silent - no console logs for timeout errors
      return Promise.reject(error);
    }

    // 504 Gateway Timeout - let the calling component show a friendly message
    if (isAxiosLikeError(error) && error.response?.status === 504) {
      return Promise.reject(error);
    }

    if (isAxiosLikeError(error) && error.response?.status === 401) {
      localStorage.removeItem("auth_session");
      localStorage.removeItem("csrf_token");
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
      return Promise.reject(error);
    }

    const responseData =
      isAxiosLikeError(error) && isPlainObject(error.response?.data)
        ? error.response.data
        : undefined;
    const message =
      (typeof responseData?.message === "string" ? responseData.message : undefined) ||
      (isAxiosLikeError(error) ? error.message : undefined) ||
      errorMessage(error) ||
      "An error occurred";

    // Only show toast for non-network and non-timeout errors
    if (code !== "ERR_NETWORK" && code !== "ECONNABORTED") {
      toast.error(message);
    }

    return Promise.reject(error);
  }
);


export { api, toastInfo };
