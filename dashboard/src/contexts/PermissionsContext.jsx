import React, { createContext, useContext, useMemo, useEffect } from 'react';
import { useAuth } from './AuthContext';
import {
  resolveUserPermissions,
  hasPermission as checkPermission,
  canManageUsers as checkCanManageUsers,
  canAccessPath,
  getDefaultPath,
  getRoles,
  migrateUsers
} from '../utils/permissions';

const PermissionsContext = createContext({});

export const usePermissions = () => useContext(PermissionsContext);

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
   * Check if current user has a specific permission
   */
  const hasPermission = (feature) => {
    return checkPermission(user, feature);
  };

  /**
   * Check if current user can manage users
   */
  const canManageUsers = () => {
    return checkCanManageUsers(user);
  };

  /**
   * Check if current user can access a path
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
