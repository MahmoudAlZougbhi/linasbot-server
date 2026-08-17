import { authFetch } from '../../utils/authFetch';

/** @param {string} path @param {RequestInit} [options] */
async function request(path, options) {
  const response = await authFetch(path, options);
  const data = await response.json();
  if (!response.ok || data.success === false) {
    throw new Error(data.error || data.detail || `Request failed (${response.status})`);
  }
  return data;
}

export const ownerApi = {
  /** @param {string} rangeKey */
  analytics: (rangeKey) => request(`/api/platform/analytics?range_key=${encodeURIComponent(rangeKey)}`),
  subscribers: () => request('/api/platform/users'),
  /** @param {string} tenantId @param {number} [limit] */
  logs: (tenantId, limit = 50) =>
    request(`/api/flow/logs?tenant_id=${encodeURIComponent(tenantId)}&limit=${limit}`),
  /** @param {string} userId @param {Record<string, unknown>} changes */
  updateUser: (userId, changes) =>
    request(`/api/platform/users/${encodeURIComponent(userId)}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),
};
