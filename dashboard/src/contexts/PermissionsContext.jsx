import { createContext, useContext, useMemo, useEffect } from "react";
import { useAuth } from './AuthContext';
import {
  resolveUserPermissions,
  canAccessPath,
  getDefaultPath,
  getRoles,
  migrateUsers
} from '../utils/permissions';

/** @type {import('react').Context<PermissionsContextValue | null>} */
const PermissionsContext = createContext(/** @type {PermissionsContextValue | null} */ (null));

export const usePermissions = () => {
  const context = useContext(PermissionsContext);
  if (!context) {
    throw new Error('usePermissions must be used within PermissionsProvider');
  }
  return context;
};

/** @param {{ children: import('react').ReactNode }} props */
export const PermissionsProvider = ({ children }) => {
  const { user } = useAuth();

  // Migrate users on first load
  useEffect(() => {
    migrateUsers();
  }, []);

  // Resolve current user's permissions
  const permissions = useMemo(() => {
    return resolveUserPermissions(user);
  }, [user]);

  // Get all available roles
  const roles = useMemo(() => {
    return getRoles();
  }, []);

  /**
   * Check if current user has a specific permission (server resolvedPermissions only).
   * @param {string} feature
   */
  const hasPermission = (feature) => {
    return user?.resolvedPermissions?.[feature] === true;
  };

  /**
   * Check if current user can manage users
   */
  const canManageUsers = () => {
    return (
      user?.resolvedPermissions?.userManagement === true ||
      user?.role === 'platform_owner'
    );
  };

  /**
   * Check if current user can access a path
   * @param {string} path
   */
  const hasAccessToPath = (path) => {
    return canAccessPath(user, path);
  };

  /**
   * Get the first accessible path for current user
   */
  const getFirstAccessiblePath = () => {
    return getDefaultPath(user);
  };

  /**
   * Check if current user is an admin
   */
  const isAdmin = () => {
    return user?.role === 'admin';
  };

  const value = {
    permissions,
    roles,
    hasPermission,
    canManageUsers,
    hasAccessToPath,
    getFirstAccessiblePath,
    isAdmin
  };

  return (
    <PermissionsContext.Provider value={value}>
      {children}
    </PermissionsContext.Provider>
  );
};

export default PermissionsContext;
