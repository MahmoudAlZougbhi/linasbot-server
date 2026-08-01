import { csrfHeaders } from './csrf';

/**
 * Fetch wrapper for dashboard APIs: cookies + CSRF on mutations.
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<Response>}
 */
export async function authFetch(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  /** @type {Record<string, string>} */
  const headers = {};
  if (options.headers) {
    if (options.headers instanceof Headers) {
      options.headers.forEach((value, key) => {
        headers[key] = value;
      });
    } else if (Array.isArray(options.headers)) {
      options.headers.forEach(([key, value]) => {
        headers[key] = value;
      });
    } else {
      Object.assign(headers, options.headers);
    }
  }
  const csrf = csrfHeaders();
  Object.assign(headers, csrf);
  if (method !== 'GET' && method !== 'HEAD' && !headers['Content-Type'] && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  return fetch(url, {
    ...options,
    method,
    credentials: 'include',
    headers,
  });
}

export default authFetch;
