import { SYSTEM_ROLES, DEFAULT_PERMISSIONS, PATH_TO_PERMISSION } from '../constants/permissions';

/**
 * System roles only. Custom roles must not come from localStorage (SEC-009).
 */
export const getRoles = () => {
  return { ...SYSTEM_ROLES };
};

/** @deprecated Custom roles localStorage removed — always empty. */
export const getCustomRoles = () => ({});

/** @deprecated No-op: custom roles are not persisted client-side. */
export const saveCustomRoles = () => {};

/**
 * Custom role mutation disabled — server is SoT for roles/permissions.
 * @param {{ name: string; description?: string; permissions?: Record<string, boolean> }} _roleData
 */
export const createCustomRole = (_roleData) => {
  throw new Error('Custom roles are disabled; use server-managed roles only');
};

/**
 * @param {string} _roleId
 * @param {Partial<RoleData>} _updates
 */
export const updateCustomRole = (_roleId, _updates) => {
  throw new Error('Custom roles are disabled; use server-managed roles only');
};

/**
 * @param {string} _roleId
 */
export const deleteCustomRole = (_roleId) => {
  throw new Error('Custom roles are disabled; use server-managed roles only');
};

/**
 * Resolve user's effective permissions
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

  // If user has custom permissions override from server payload, use those
  if (user.permissions) {
    return { ...DEFAULT_PERMISSIONS, ...user.permissions };
  }

  const roles = getRoles();
  const role = user.role ? roles[user.role] : undefined;

  if (role) {
    return { ...role.permissions };
  }

  return { ...DEFAULT_PERMISSIONS };
};

/**
 * Check if user has a specific permission
 * @param {AuthUser | DashboardUser | null | undefined} user
 * @param {string} feature
 */
export const hasPermission = (user, feature) => {
  const permissions = resolveUserPermissions(user);
  return permissions[feature] === true;
};

/**
 * Check if user can access a specific path
 * @param {AuthUser | DashboardUser | null | undefined} user
 * @param {string} path
 */
export const canAccessPath = (user, path) => {
  /** @type {Record<string, string>} */
  const pathMap = PATH_TO_PERMISSION;
  const permissionKey = pathMap[path];
  if (permissionKey) {
    return hasPermission(user, permissionKey);
  }
  // Nested CM routes share the contentManagers permission.
  if (path.startsWith('/content-managers/')) {
    return hasPermission(user, 'contentManagers');
  }
  // If path is not in the map, allow access (public or unknown route)
  return true;
};

/**
 * Get the first accessible path for a user
 * @param {AuthUser | DashboardUser | null | undefined} user
 */
export const getDefaultPath = (user) => {
  // Landing-only SPA: operator paths redirect to get-app; prefer thin auth home.
  const paths = ['/', '/login', '/app', '/live-chat', '/content-managers', '/settings', '/activity-flow'];

  for (const path of paths) {
    if (canAccessPath(user, path)) {
      return path;
    }
  }

  return '/';
};

/**
 * Legacy localStorage users_db migration — no longer invents role=admin.
 * Clears stale custom_roles_db if present.
 */
export const migrateUsers = () => {
  try {
    localStorage.removeItem('custom_roles_db');
    const stored = localStorage.getItem('users_db');
    if (!stored) return;

    const users = JSON.parse(stored);
    let migrated = false;

    const updatedUsers = users.map((/** @type {Record<string, unknown>} */ user) => {
      if (user.status !== undefined) {
        return user;
      }

      migrated = true;
      const role = typeof user.role === 'string' && user.role ? user.role : 'viewer';
      return {
        ...user,
        role,
        permissions: null,
        status: 'active',
        lastLogin: null,
        createdBy: null,
        updatedAt: user.createdAt || new Date().toISOString()
      };
    });

    if (migrated) {
      localStorage.setItem('users_db', JSON.stringify(updatedUsers));
    }

    return updatedUsers;
  } catch (error) {
    console.error('Failed to migrate users:', error);
    return [];
  }
};

/**
 * Check if user can manage other users
 * @param {AuthUser | DashboardUser | null | undefined} user
 */
export const canManageUsers = (user) => {
  return hasPermission(user, 'userManagement');
};

/**
 * Get accessible navigation items for a user
 * @param {AuthUser | DashboardUser | null | undefined} user
 * @param {Array<{ href: string; [key: string]: unknown }>} navigationItems
 */
export const getAccessibleNavigation = (user, navigationItems) => {
  /** @type {Record<string, string>} */
  const pathMap = PATH_TO_PERMISSION;
  return navigationItems.filter(item => {
    const permissionKey = pathMap[item.href];
    if (!permissionKey) return true;
    return hasPermission(user, permissionKey);
  });
};
