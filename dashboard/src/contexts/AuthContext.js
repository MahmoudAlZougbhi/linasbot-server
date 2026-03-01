import React, { createContext, useState, useContext, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { resolveUserPermissions } from '../utils/permissions';

const AuthContext = createContext({});

export const useAuth = () => useContext(AuthContext);

// API base URL - uses proxy in development
const API_BASE = '/api/auth';

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  // Check for existing session on mount
  useEffect(() => {
    let cancelled = false;
    const safetyTimeout = setTimeout(() => {
      if (!cancelled) {
        setLoading(false);
        cancelled = true;
      }
    }, 5000); // Never block more than 5s - show login if backend unreachable

    checkSession()
      .finally(() => {
        if (!cancelled) {
          clearTimeout(safetyTimeout);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      clearTimeout(safetyTimeout);
    };
  }, []);

  const checkSession = async () => {
    try {
      const session = localStorage.getItem('auth_session');
      if (session) {
        const sessionData = JSON.parse(session);
        const sessionTime = new Date(sessionData.timestamp);
        const now = new Date();
        const hoursDiff = (now - sessionTime) / (1000 * 60 * 60);

        // Check if session is less than 24 hours old
        if (hoursDiff < 24 && sessionData.user?.id) {
          // Validate session with backend and get fresh user data (5s timeout for local)
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 5000);
          const response = await fetch(`${API_BASE}/session/${sessionData.user.id}`, {
            signal: controller.signal
          });
          clearTimeout(timeoutId);
          const data = await response.json();

          if (data.success && data.user && data.user.status === 'active') {
            const userData = buildUserData(data.user);
            setUser(userData);

            // Update session with fresh data
            const newSession = {
              user: userData,
              timestamp: new Date().toISOString()
            };
            localStorage.setItem('auth_session', JSON.stringify(newSession));
          } else {
            // Session invalid, clear it
            localStorage.removeItem('auth_session');
          }
        } else {
          localStorage.removeItem('auth_session');
        }
      }
    } catch (error) {
      console.error('Session check failed:', error);
      localStorage.removeItem('auth_session');
    }
  };

  const buildUserData = (user) => {
    const permissions = resolveUserPermissions(user);
    return {
      id: user.id,
      email: user.email,
      name: user.name || user.email.split('@')[0],
      role: user.role || 'admin',
      permissions: user.permissions,
      resolvedPermissions: permissions,
      status: user.status || 'active',
      lastLogin: user.lastLogin,
      createdAt: user.createdAt
    };
  };

  const login = async (email, password) => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);
      const response = await fetch(`${API_BASE}/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email, password }),
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Login failed');
      }

      const userData = buildUserData(data.user);

      // Create session
      const session = {
        user: userData,
        timestamp: new Date().toISOString()
      };

      localStorage.setItem('auth_session', JSON.stringify(session));
      setUser(userData);

      toast.success('Welcome back!');
      navigate('/');

      return userData;
    } catch (error) {
      const msg = error.name === 'AbortError'
        ? 'Connection timed out. Is the backend running on port 8003?'
        : (error.message || 'Login failed');
      toast.error(msg);
      throw new Error(msg);
    }
  };

  const logout = () => {
    localStorage.removeItem('auth_session');
    setUser(null);
    navigate('/login');
    toast.success('Logged out successfully');
  };

  const changePassword = async (currentPassword, newPassword) => {
    try {
      if (!user) throw new Error('Not authenticated');

      const response = await fetch(`${API_BASE}/change-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: user.id,
          current_password: currentPassword,
          new_password: newPassword
        })
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to change password');
      }

      toast.success('Password changed successfully');
      return true;
    } catch (error) {
      toast.error(error.message || 'Failed to change password');
      throw error;
    }
  };

  // ============================================
  // User Management Functions (CRUD)
  // ============================================

  /**
   * Get all users (without passwords)
   */
  const getUsers = async () => {
    try {
      const response = await fetch(`${API_BASE}/users`);
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
  const createUser = async (userData) => {
    if (!user) throw new Error('Not authenticated');

    // Check if current user can manage users
    if (user.resolvedPermissions?.userManagement !== true && user.role !== 'admin') {
      throw new Error('Permission denied');
    }

    try {
      const response = await fetch(`${API_BASE}/users?created_by=${user.id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email: userData.email,
          password: userData.password,
          name: userData.name || userData.email.split('@')[0],
          role: userData.role || 'viewer',
          permissions: userData.permissions || null,
          status: userData.status || 'active'
        })
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to create user');
      }

      return data.user;
    } catch (error) {
      throw error;
    }
  };

  /**
   * Update a user
   */
  const updateUser = async (userId, updates) => {
    if (!user) throw new Error('Not authenticated');

    // Check if current user can manage users
    if (user.resolvedPermissions?.userManagement !== true && user.role !== 'admin') {
      throw new Error('Permission denied');
    }

    try {
      const response = await fetch(`${API_BASE}/users/${userId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(updates)
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to update user');
      }

      // If updating current user, refresh session
      if (userId === user.id) {
        const updatedUserData = buildUserData(data.user);
        setUser(updatedUserData);

        const session = {
          user: updatedUserData,
          timestamp: new Date().toISOString()
        };
        localStorage.setItem('auth_session', JSON.stringify(session));
      }

      return data.user;
    } catch (error) {
      throw error;
    }
  };

  /**
   * Delete a user
   */
  const deleteUser = async (userId) => {
    if (!user) throw new Error('Not authenticated');

    // Check if current user can manage users
    if (user.resolvedPermissions?.userManagement !== true && user.role !== 'admin') {
      throw new Error('Permission denied');
    }

    // Cannot delete yourself
    if (userId === user.id) {
      throw new Error('Cannot delete your own account');
    }

    try {
      const response = await fetch(`${API_BASE}/users/${userId}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to delete user');
      }

      return true;
    } catch (error) {
      throw error;
    }
  };

  /**
   * Refresh current user's data from backend
   */
  const refreshUser = async () => {
    if (!user) return;

    try {
      const response = await fetch(`${API_BASE}/session/${user.id}`);
      const data = await response.json();

      if (data.success && data.user) {
        const userData = buildUserData(data.user);
        setUser(userData);

        const session = {
          user: userData,
          timestamp: new Date().toISOString()
        };
        localStorage.setItem('auth_session', JSON.stringify(session));
      }
    } catch (error) {
      console.error('Failed to refresh user:', error);
    }
  };

  const value = {
    user,
    login,
    logout,
    changePassword,
    loading,
    // User management
    getUsers,
    createUser,
    updateUser,
    deleteUser,
    refreshUser
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
