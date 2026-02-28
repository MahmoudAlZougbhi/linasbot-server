import { useAuth } from '../../contexts/AuthContext';
import { hasPermission } from '../../utils/permissions';

/**
 * PermissionGate - Conditionally renders children based on user permissions
 *
 * @param {string} permission - The permission key to check (e.g., 'userManagement', 'training')
 * @param {React.ReactNode} children - Content to render if user has permission
 * @param {React.ReactNode} fallback - Optional content to render if user lacks permission
 * @param {boolean} requireAdmin - If true, only admins can see the content
 */
const PermissionGate = ({
  permission,
  children,
  fallback = null,
  requireAdmin = false
}) => {
  const { user } = useAuth();

  // No user - don't render
  if (!user) {
    return fallback;
  }

  // Admin check
  if (requireAdmin && user.role !== 'admin') {
    return fallback;
  }

  // Permission check
  if (permission) {
    const hasAccess = hasPermission(user, permission);
    if (!hasAccess && user.role !== 'admin') {
      return fallback;
    }
  }

  return children;
};

/**
 * usePermissionGate - Hook version for programmatic permission checks
 */
export const usePermissionGate = () => {
  const { user } = useAuth();

  const checkPermission = (permission) => {
    if (!user) return false;
    if (user.role === 'admin') return true;
    return hasPermission(user, permission);
  };

  const checkAdmin = () => {
    return user?.role === 'admin';
  };

  return {
    checkPermission,
    checkAdmin,
    user
  };
};

export default PermissionGate;
