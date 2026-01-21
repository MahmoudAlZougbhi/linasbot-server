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

  /**
   * Check if current user can access a specific path
   */
  const hasAccessToPath = useCallback((path) => {
    return canAccessPath(user, path);
  }, [user]);

  /**
   * Get the first accessible path for current user
   */
  const getFirstAccessiblePath = useCallback(() => {
    return getDefaultPath(user);
  }, [user]);

  /**
   * Check if current user has a specific permission
   */
  const checkPermission = useCallback((feature) => {
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
