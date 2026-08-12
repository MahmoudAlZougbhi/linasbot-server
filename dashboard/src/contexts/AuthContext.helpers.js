import { resolveUserPermissions } from '../utils/permissions';
import { csrfHeaders } from '../utils/csrf';

// API base - fixed relative path (same as last working commit d9a0000)
export const API_BASE = '/api/auth';
export const SESSION_VALIDATE_MIN_INTERVAL_MS = 10 * 60 * 1000; // 10 minutes

/** @param {RequestInit} [options] @returns {RequestInit} */
export const withAuthFetch = (options = {}) => {
  const headers = new Headers(options.headers || {});
  const csrf = csrfHeaders();
  Object.entries(csrf).forEach(([key, value]) => {
    if (typeof value === 'string') headers.set(key, value);
  });
  return {
    credentials: 'include',
    ...options,
    headers,
  };
};

/**
 * @param {unknown} user
 * @returns {AuthUser | null}
 */
export const buildUserData = (user) => {
  if (!user || typeof user !== 'object') {
    console.warn('[AuthContext] buildUserData called with invalid user:', user);
    return null;
  }
  const record = /** @type {Record<string, unknown>} */ (user);
  const role = typeof record.role === 'string' ? record.role.trim() : '';
  const tenantId = typeof record.tenantId === 'string' ? record.tenantId.trim() : '';
  if (!role || !tenantId) {
    console.warn('[AuthContext] buildUserData incomplete session: missing role or tenantId');
    return null;
  }
  const email = typeof record.email === 'string' ? record.email : '';
  const name =
    (typeof record.name === 'string' && record.name) ||
    (email ? (email.split('@')[0] ?? 'user') : 'user');
  const permissions = resolveUserPermissions(/** @type {AuthUser} */ (/** @type {unknown} */ (record)));
  return {
    id: typeof record.id === 'string' ? record.id : undefined,
    email,
    name,
    role,
    permissions: /** @type {AuthUser['permissions']} */ (record.permissions ?? null),
    resolvedPermissions: permissions,
    status: typeof record.status === 'string' ? record.status : 'active',
    lastLogin: typeof record.lastLogin === 'string' ? record.lastLogin : null,
    createdAt: typeof record.createdAt === 'string' ? record.createdAt : null,
    tenantId,
    emailVerified: record.emailVerified === true,
  };
};
