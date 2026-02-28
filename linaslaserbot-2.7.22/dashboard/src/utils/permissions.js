import { SYSTEM_ROLES, DEFAULT_PERMISSIONS, PATH_TO_PERMISSION } from '../constants/permissions';

const CUSTOM_ROLES_KEY = 'custom_roles_db';

/**
 * Get all roles (system + custom)
 */
export const getRoles = () => {
  const customRoles = getCustomRoles();
  return { ...SYSTEM_ROLES, ...customRoles };
};

/**
 * Get custom roles from localStorage
 */
export const getCustomRoles = () => {
  try {
    const stored = localStorage.getItem(CUSTOM_ROLES_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch (error) {
    console.error('Failed to get custom roles:', error);
    return {};
  }
};

/**
 * Save custom roles to localStorage
 */
export const saveCustomRoles = (roles) => {
  try {
    localStorage.setItem(CUSTOM_ROLES_KEY, JSON.stringify(roles));
  } catch (error) {
    console.error('Failed to save custom roles:', error);
  }
};

/**
 * Create a new custom role
 */
export const createCustomRole = (roleData) => {
  const customRoles = getCustomRoles();
  const id = `custom_${Date.now()}`;
  const newRole = {
    id,
    name: roleData.name,
    description: roleData.description || '',
    isSystem: false,
    permissions: { ...DEFAULT_PERMISSIONS, ...roleData.permissions }
  };
  customRoles[id] = newRole;
  saveCustomRoles(customRoles);
  return newRole;
};

/**
 * Update a custom role
 */
export const updateCustomRole = (roleId, updates) => {
  const customRoles = getCustomRoles();
  if (customRoles[roleId]) {
    customRoles[roleId] = { ...customRoles[roleId], ...updates };
    saveCustomRoles(customRoles);
    return customRoles[roleId];
  }
  return null;
};

/**
 * Delete a custom role
 */
export const deleteCustomRole = (roleId) => {
  const customRoles = getCustomRoles();
  if (customRoles[roleId] && !customRoles[roleId].isSystem) {
    delete customRoles[roleId];
    saveCustomRoles(customRoles);
    return true;
  }
  return false;
};

/**
 * Resolve user's effective permissions
 * If user has custom permissions, use those; otherwise use role defaults
 */
export const resolveUserPermissions = (user) => {
  if (!user) {
    return { ...DEFAULT_PERMISSIONS };
  }

  // If user has custom permissions override, use those
  if (user.permissions) {
    return { ...DEFAULT_PERMISSIONS, ...user.permissions };
  }

  // Otherwise, get permissions from role
  const roles = getRoles();
  const role = roles[user.role];

  if (role) {
    return { ...role.permissions };
  }

  // Fallback to default (all denied)
  return { ...DEFAULT_PERMISSIONS };
};

/**
 * Check if user has a specific permission
 */
export const hasPermission = (user, feature) => {
  const permissions = resolveUserPermissions(user);
  return permissions[feature] === true;
};

/**
 * Check if user can access a specific path
 */
export const canAccessPath = (user, path) => {
  const permissionKey = PATH_TO_PERMISSION[path];
  if (!permissionKey) {
    // If path is not in the map, allow access (public or unknown route)
    return true;
  }
  return hasPermission(user, permissionKey);
};

/**
 * Get the first accessible path for a user
 */
export const getDefaultPath = (user) => {
  const paths = ['/', '/live-chat', '/chat-history', '/training', '/testing', '/analytics', '/smart-messaging', '/settings'];

  for (const path of paths) {
    if (canAccessPath(user, path)) {
      return path;
    }
  }

  // If no path is accessible, return root (this shouldn't happen for valid users)
  return '/';
};

/**
 * Migrate existing users to new schema with permissions fields
 */
export const migrateUsers = () => {
  try {
    const stored = localStorage.getItem('users_db');
    if (!stored) return;

    const users = JSON.parse(stored);
    let migrated = false;

    const updatedUsers = users.map(user => {
      // Skip if already migrated
      if (user.status !== undefined) {
        return user;
      }

      migrated = true;
      return {
        ...user,
        role: user.role || 'admin', // Preserve existing access
        permissions: null, // No custom overrides
        status: 'active',
        lastLogin: null,
        createdBy: null,
        updatedAt: user.createdAt || new Date().toISOString()
      };
    });

    if (migrated) {
      localStorage.setItem('users_db', JSON.stringify(updatedUsers));
      console.log('Users migrated to new permissions schema');
    }

    return updatedUsers;
  } catch (error) {
    console.error('Failed to migrate users:', error);
    return [];
  }
};

/**
 * Check if user can manage other users
 */
export const canManageUsers = (user) => {
  return hasPermission(user, 'userManagement');
};

/**
 * Get accessible navigation items for a user
 */
export const getAccessibleNavigation = (user, navigationItems) => {
  return navigationItems.filter(item => {
    const permissionKey = PATH_TO_PERMISSION[item.href];
    if (!permissionKey) return true;
    return hasPermission(user, permissionKey);
  });
};
