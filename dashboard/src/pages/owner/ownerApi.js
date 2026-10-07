import { authFetch } from '../../utils/authFetch';

/** @param {string} path @param {RequestInit} [options] */
async function request(path, options) {
  const response = await authFetch(path, options);
  const text = await response.text();
  /** @type {any} */
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(`The portal could not read this response (${response.status}).`);
    }
  }
  if (!response.ok || data.success === false) {
    throw new Error(data.error || data.detail || `Request failed (${response.status})`);
  }
  return data;
}

export const ownerApi = {
  /** @param {string} rangeKey */
  analytics: (rangeKey) => request(`/api/platform/analytics?range_key=${encodeURIComponent(rangeKey)}`),
  subscribers: (cursor = '') => {
    const params = new URLSearchParams();
    if (cursor) params.set('cursor', cursor);
    const query = params.toString();
    return request(query ? `/api/platform/users?${query}` : '/api/platform/users');
  },
  /** @param {string} tenantId @param {number} [limit] */
  logs: (tenantId, limit = 50) =>
    request(`/api/flow/logs?tenant_id=${encodeURIComponent(tenantId)}&limit=${limit}`),
  /** @param {string} userId @param {Record<string, unknown>} changes */
  updateUser: (userId, changes) =>
    request(`/api/platform/users/${encodeURIComponent(userId)}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),
  activationReadiness: () => request('/api/platform/activation-readiness'),
  messageCatalog: () => request('/api/platform/message-catalog'),
  /** @param {Record<string, unknown>} body */
  updateMessageCatalog: (body) =>
    request('/api/platform/message-catalog', { method: 'PATCH', body: JSON.stringify(body) }),
  publishMessageCatalog: () => request('/api/platform/message-catalog/publish', { method: 'POST', body: '{}' }),
  /** @param {Record<string, string>} [filters] */
  costs: (filters = {}) => {
    const params = new URLSearchParams(
      Object.fromEntries(Object.entries(filters).filter(([, value]) => value)),
    );
    const query = params.toString();
    return request(query ? `/api/platform/costs?${query}` : '/api/platform/costs');
  },
  conversionDryRun: () => request('/api/platform/credit-conversion/dry-run'),
  /** @param {string} tenantId */
  messageLedger: (tenantId) => request(`/api/platform/message-ledger/${encodeURIComponent(tenantId)}`),
  /**
   * @param {string} tenantId
   * @param {Record<string, string>} [filters]
   */
  tenantCosts: (tenantId, filters = {}) => {
    const params = new URLSearchParams(
      Object.fromEntries(Object.entries(filters).filter(([, value]) => value)),
    );
    const query = params.toString();
    return request(
      query
        ? `/api/platform/costs/tenants/${encodeURIComponent(tenantId)}?${query}`
        : `/api/platform/costs/tenants/${encodeURIComponent(tenantId)}`,
    );
  },
  /** @param {{ tenant_id?: string, limit: number, reason?: string }} body */
  patchDailyEdits: (body) =>
    request('/api/platform/daily-edits', { method: 'PATCH', body: JSON.stringify(body) }),
  /** @param {string} tenantId */
  reindexTenant: (tenantId) =>
    request(`/api/platform/customer-ai-index/${encodeURIComponent(tenantId)}/reindex`, {
      method: 'POST',
      body: '{}',
    }),
  /** @param {{ tenant_id?: string, limit?: number }} [filters] */
  messageFlows: (filters = {}) => {
    const params = new URLSearchParams(
      Object.fromEntries(
        Object.entries(filters)
          .filter(([, value]) => value !== undefined && value !== null && String(value) !== '')
          .map(([key, value]) => [key, String(value)]),
      ),
    );
    const query = params.toString();
    return request(query ? `/api/platform/message-flows?${query}` : '/api/platform/message-flows');
  },
  /** @param {string} tenantId @param {string} operationId */
  messageFlow: (tenantId, operationId) =>
    request(`/api/platform/message-flows/${encodeURIComponent(tenantId)}/${encodeURIComponent(operationId)}`),
  /**
   * @param {'customer' | 'copilot'} brain
   * @param {{ tenant_id: string, message: string, history: { role: string, text: string }[] }} body
   */
  brainTurn: (brain, body) =>
    request(`/api/platform/brains/${brain}`, { method: 'POST', body: JSON.stringify(body) }),
};
