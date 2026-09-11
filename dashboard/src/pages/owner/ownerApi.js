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
  /** @param {string} tenantId @param {Record<string, string>} [filters] */
  conversionDryRun: () => request('/api/platform/credit-conversion/dry-run'),
  messageLedger: (tenantId) => request(`/api/platform/message-ledger/${encodeURIComponent(tenantId)}`),
  /** @param {{ tenant_id: string, message: string, conversation_id?: string, user_id?: string, channel?: string, message_id?: string, history?: object[] }} body */
  labTurn: (body) =>
    request('/api/platform/customer-ai-lab/turn', { method: 'POST', body: JSON.stringify(body) }),
  labEvals: () => request('/api/platform/customer-ai-lab/evals'),
  /** @param {{ generated?: boolean, faq_used?: boolean, followup_sent?: boolean }} body */
  labClassify: (body) =>
    request('/api/platform/customer-ai-lab/classify', { method: 'POST', body: JSON.stringify(body) }),
  /** @param {{ tenant_id?: string, limit: number, reason?: string }} body */
  patchDailyEdits: (body) =>
    request('/api/platform/daily-edits', { method: 'PATCH', body: JSON.stringify(body) }),
  /** @param {string} tenantId */
  reindexTenant: (tenantId) =>
    request(`/api/platform/customer-ai-index/${encodeURIComponent(tenantId)}/reindex`, {
      method: 'POST',
      body: '{}',
    }),
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
};
