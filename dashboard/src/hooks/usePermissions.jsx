import { useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
  canAccessPath,
  getDefaultPath,
  hasPermission,
  resolveUserPermissions,
  canManageUsers
} from '../utils/permissions';

/**
 * Custom hook for permission-related operations
 */
export const usePermissionsHook = () => {
  const { user } = useAuth();

  const hasAccessToPath = useCallback((/** @type {string} */ path) => {
    return canAccessPath(user, path);
  }, [user]);

  const getFirstAccessiblePath = useCallback(() => {
    return getDefaultPath(user);
  }, [user]);

  const checkPermission = useCallback((/** @type {string} */ feature) => {
    return hasPermission(user, feature);
  }, [user]);

  /**
   * Get all resolved permissions for current user
   */
  const getPermissions = useCallback(() => {
    return resolveUserPermissions(user);
  }, [user]);

  /**
   * Check if current user can manage users
   */
  const checkCanManageUsers = useCallback(() => {
    return canManageUsers(user);
  }, [user]);

  /**
   * Check if current user is an admin
   */
  const isAdmin = useCallback(() => {
    return user?.role === 'admin';
  }, [user]);

  return {
    hasAccessToPath,
    getFirstAccessiblePath,
    checkPermission,
    getPermissions,
    canManageUsers: checkCanManageUsers,
    isAdmin,
    user
  };
};

export default usePermissionsHook;
