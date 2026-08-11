import toast from 'react-hot-toast';
import { errorMessage } from '../utils/apiValidate';
import { API_BASE, buildUserData, withAuthFetch } from './AuthContext.helpers';

/**
 * @param {{
 *   user: AuthUser | null;
 *   setUser: import('react').Dispatch<import('react').SetStateAction<AuthUser | null>>;
 * }} deps
 */
export const createAuthUserManagement = ({ user, setUser }) => {
  const getUsers = async () => {
    try {
      const response = await fetch(`${API_BASE}/users`, withAuthFetch());
      const data = await response.json();
  
      if (!data.success) {
        throw new Error(data.error || 'Failed to fetch users');
      }
  
      return data.users;
    } catch (error) {
      console.error('Failed to fetch users:', error);
      throw error;
    }
  };
  
  /**
   * Create a new user
   */
  const createUser = async (/** @type {Record<string, unknown>} */ userData) => {
    if (!user) throw new Error('Not authenticated');
  
    // Check if current user can manage users
    if (user.resolvedPermissions?.userManagement !== true && user.role !== 'admin') {
      throw new Error('Permission denied');
    }
  
    const response = await fetch(`${API_BASE}/users?created_by=${user.id}`, withAuthFetch({
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        email: typeof userData.email === 'string' ? userData.email : '',
        password: typeof userData.password === 'string' ? userData.password : '',
        name: typeof userData.name === 'string'
          ? userData.name
          : (typeof userData.email === 'string' ? userData.email.split('@')[0] : 'user'),
        role: typeof userData.role === 'string' ? userData.role : 'viewer',
        permissions: userData.permissions ?? null,
        status: typeof userData.status === 'string' ? userData.status : 'active'
      })
    }));
  
    const data = await response.json();
  
    if (!data.success) {
      throw new Error(data.error || 'Failed to create user');
    }
  
    return data.user;
  };
  
  /**
   * Update a user
   */
  const updateUser = async (
    /** @type {string} */ userId,
    /** @type {Record<string, unknown>} */ updates
  ) => {
    if (!user) throw new Error('Not authenticated');
  
    // Check if current user can manage users
    if (user.resolvedPermissions?.userManagement !== true && user.role !== 'admin') {
      throw new Error('Permission denied');
    }
  
    const response = await fetch(`${API_BASE}/users/${userId}`, withAuthFetch({
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(updates)
    }));
  
    const data = await response.json();
  
    if (!data.success) {
      throw new Error(data.error || 'Failed to update user');
    }
  
    // If updating current user, refresh session
    if (userId === user.id && data.user) {
      const updatedUserData = buildUserData(data.user);
      if (!updatedUserData) return data.user;
      setUser(updatedUserData);
  
      const session = {
        user: updatedUserData,
        timestamp: new Date().toISOString(),
        lastValidatedAt: new Date().toISOString()
      };
      localStorage.setItem('auth_session', JSON.stringify(session));
    }
  
    return data.user;
  };
  
  /**
   * Delete a user
   */
  const deleteUser = async (/** @type {string} */ userId) => {
    if (!user) throw new Error('Not authenticated');
  
    // Check if current user can manage users
    if (user.resolvedPermissions?.userManagement !== true && user.role !== 'admin') {
      throw new Error('Permission denied');
    }
  
    // Cannot delete yourself
    if (userId === user.id) {
      throw new Error('Cannot delete your own account');
    }
  
    const response = await fetch(`${API_BASE}/users/${userId}`, withAuthFetch({
      method: 'DELETE'
    }));
  
    const data = await response.json();
  
    if (!data.success) {
      throw new Error(data.error || 'Failed to delete user');
    }
  
    return true;
  };
  
  /**
   * Refresh current user's data from backend
   */
  const refreshUser = async () => {
    if (!user) return;
  
    try {
      const response = await fetch(`${API_BASE}/session`, withAuthFetch());
      const data = await response.json();
  
      if (data.success && data.user && typeof data.user === 'object') {
        const userData = buildUserData(data.user);
        if (userData) {
          setUser(userData);
          const session = {
            user: userData,
          timestamp: new Date().toISOString(),
          lastValidatedAt: new Date().toISOString()
          };
          localStorage.setItem('auth_session', JSON.stringify(session));
        }
      }
    } catch (error) {
      console.error('Failed to refresh user:', error);
    }
  };

  return {
    getUsers,
    createUser,
    updateUser,
    deleteUser,
    refreshUser,
  };
};
