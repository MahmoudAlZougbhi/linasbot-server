import { API_BASE, buildUserData, withAuthFetch } from './AuthContext.helpers';

/**
 * Session refresh only. Tenant user CRUD lives in the mobile app via /api/auth/users.
 * @param {{
 *   user: AuthUser | null;
 *   setUser: import('react').Dispatch<import('react').SetStateAction<AuthUser | null>>;
 * }} deps
 */
export const createAuthUserManagement = ({ user, setUser }) => {
  const refreshUser = async () => {
    if (!user) return;

    try {
      const response = await fetch(`${API_BASE}/session`, withAuthFetch());
      const data = await response.json();

      if (data.success && data.user && typeof data.user === 'object') {
        const userData = buildUserData(data.user);
        if (userData) {
          setUser(userData);
          localStorage.setItem(
            'auth_session',
            JSON.stringify({
              user: userData,
              timestamp: new Date().toISOString(),
              lastValidatedAt: new Date().toISOString(),
            })
          );
        }
      }
    } catch (error) {
      console.error('Failed to refresh user:', error);
    }
  };

  return { refreshUser };
};
