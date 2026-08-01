import { csrfHeaders } from './csrf';

/**
 * Fetch wrapper for dashboard APIs: cookies + CSRF on mutations.
 */
export async function authFetch(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = {
    ...(options.headers || {}),
    ...csrfHeaders(),
  };
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
