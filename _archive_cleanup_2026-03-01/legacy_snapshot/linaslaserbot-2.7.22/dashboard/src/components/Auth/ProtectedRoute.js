import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { canAccessPath, getDefaultPath } from '../../utils/permissions';
import LoadingScreen from '../Common/LoadingScreen';

const ProtectedRoute = ({ children, requiredPermission }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <LoadingScreen />;
  }

  // Not authenticated - redirect to login
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // Check specific permission if provided
  if (requiredPermission) {
    const hasPermission = user.resolvedPermissions?.[requiredPermission] === true;
    if (!hasPermission && user.role !== 'admin') {
      const defaultPath = getDefaultPath(user);
      return <Navigate to={defaultPath} replace />;
    }
  }

  // Check path-based permissions
  const currentPath = location.pathname;
  if (!canAccessPath(user, currentPath)) {
    const defaultPath = getDefaultPath(user);
    // Prevent redirect loop
    if (defaultPath !== currentPath) {
      return <Navigate to={defaultPath} replace />;
    }
  }

  return children;
};

export default ProtectedRoute;
