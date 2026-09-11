import { SYSTEM_ROLES, DEFAULT_PERMISSIONS } from '../constants/permissions';

/**
 * System roles only. Custom roles must not come from localStorage (SEC-009).
 */
export const getRoles = () => {
  return { ...SYSTEM_ROLES };
};

/**
 * Resolve user's effective permissions for the login session object.
 * Prefer server resolvedPermissions; else role defaults; never invent admin.
 * @param {AuthUser | DashboardUser | null | undefined} user
 */
export const resolveUserPermissions = (user) => {
  if (!user) {
    return { ...DEFAULT_PERMISSIONS };
  }

  if (user.resolvedPermissions && typeof user.resolvedPermissions === 'object') {
    return { ...DEFAULT_PERMISSIONS, ...user.resolvedPermissions };
  }

  if (user.permissions) {
    return { ...DEFAULT_PERMISSIONS, ...user.permissions };
  }

  const roles = /** @type {Record<string, { permissions: Record<string, boolean> }>} */ (getRoles());
  const role = user.role ? roles[user.role] : undefined;

  if (role) {
    return { ...role.permissions };
  }

  return { ...DEFAULT_PERMISSIONS };
};
