import React, { createContext, useState, useContext, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { resolveUserPermissions } from '../utils/permissions';

const AuthContext = createContext({});

export const useAuth = () => useContext(AuthContext);

// API base - fixed relative path (same as last working commit d9a0000)
const API_BASE = '/api/auth';
const SESSION_VALIDATE_MIN_INTERVAL_MS = 10 * 60 * 1000; // 10 minutes

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
        const lastValidatedAt = sessionData.lastValidatedAt
          ? new Date(sessionData.lastValidatedAt)
          : null;
        const validatedRecently = lastValidatedAt
          ? (now - lastValidatedAt) < SESSION_VALIDATE_MIN_INTERVAL_MS
          : false;

        // Check if session is less than 24 hours old
        if (hoursDiff < 24 && sessionData.user?.id) {
          if (validatedRecently) {
            const cachedUser = buildUserData(sessionData.user);
            if (cachedUser) {
              setUser(cachedUser);
              return;
            }
          }
          // Validate session with backend and get fresh user data (5s timeout for local)
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 5000);
          const response = await fetch(`${API_BASE}/session/${sessionData.user.id}`, {
            signal: controller.signal
          });
          clearTimeout(timeoutId);
          const data = await response.json();
          const authErrorText = String(data?.error || '').toLowerCase();
          const transientSessionError = (
            authErrorText.includes('quota')
            || authErrorText.includes('429')
            || authErrorText.includes('resource exhausted')
            || authErrorText.includes('timeout')
            || authErrorText.includes('unavailable')
          );

          console.log('[AuthContext] checkSession response:', JSON.stringify({ success: data?.success, hasUser: !!data?.user, userStatus: data?.user?.status }));

          if (!data.success || !data.user || typeof data.user !== 'object') {
            if (transientSessionError && sessionData.user) {
              const cachedUser = buildUserData(sessionData.user);
              if (cachedUser) {
                console.warn('[AuthContext] checkSession transient error, using cached session user');
                setUser(cachedUser);
                return;
              }
            }
            console.warn('[AuthContext] checkSession: invalid or missing user data', data);
            localStorage.removeItem('auth_session');
            return;
          }
          if (data.user.status !== 'active') {
            console.warn('[AuthContext] checkSession: user status not active', data.user.status);
            localStorage.removeItem('auth_session');
            return;
          }

          const userData = buildUserData(data.user);
          if (!userData) {
            console.warn('[AuthContext] checkSession: buildUserData returned null', data.user);
            localStorage.removeItem('auth_session');
            return;
          }

          setUser(userData);
          const newSession = {
            user: userData,
            timestamp: new Date().toISOString(),
            lastValidatedAt: new Date().toISOString()
          };
          localStorage.setItem('auth_session', JSON.stringify(newSession));
        } else {
          localStorage.removeItem('auth_session');
        }
      }
    } catch (error) {
      console.error('Session check failed:', error);
      // Fail-open on transient backend issues: keep cached session if valid.
      try {
        const session = localStorage.getItem('auth_session');
        if (session) {
          const sessionData = JSON.parse(session);
          const sessionTime = new Date(sessionData.timestamp);
          const now = new Date();
          const hoursDiff = (now - sessionTime) / (1000 * 60 * 60);
          if (hoursDiff < 24 && sessionData.user?.id) {
            const cachedUser = buildUserData(sessionData.user);
            if (cachedUser) {
              console.warn('[AuthContext] using cached session after checkSession failure');
              setUser(cachedUser);
              return;
            }
          }
        }
      } catch (cacheErr) {
        // Ignore fallback parse errors and clear invalid session below.
      }
      localStorage.removeItem('auth_session');
    }
  };

  const buildUserData = (user) => {
    if (!user || typeof user !== 'object') {
      console.warn('[AuthContext] buildUserData called with invalid user:', user);
      return null;
    }
    const email = user.email ?? '';
    const name = user.name || (email ? email.split('@')[0] : 'user');
    const permissions = resolveUserPermissions(user);
    return {
      id: user.id,
      email,
      name,
      role: user.role || 'admin',
      permissions: user.permissions,
      resolvedPermissions: permissions,
      status: user.status || 'active',
      lastLogin: user.lastLogin,
      createdAt: user.createdAt
    };
  };

  const TRANSIENT_AUTH_ERROR = 'Authentication service temporarily unavailable';

  const login = async (email, password, redirectTo = '/', retryCount = 0) => {
    const maxRetries = 2;
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

      // Debug: log exact auth response shape before processing
      console.log('[AuthContext] login response:', JSON.stringify({ success: data?.success, hasUser: !!data?.user, userKeys: data?.user ? Object.keys(data.user) : [] }));

      if (!data.success) {
        const errMsg = data.error || 'Login failed';
        if (errMsg.includes(TRANSIENT_AUTH_ERROR) && retryCount < maxRetries) {
          toast.loading(`Service temporarily unavailable. Retrying in 3s... (${retryCount + 1}/${maxRetries})`, { id: 'auth-retry' });
          await new Promise((r) => setTimeout(r, 3000));
          toast.dismiss('auth-retry');
          return login(email, password, redirectTo, retryCount + 1);
        }
        throw new Error(errMsg);
      }

      if (!data.user || typeof data.user !== 'object') {
        console.error('[AuthContext] login failed: data.user missing or invalid', data);
        throw new Error('Invalid login response: missing user data');
      }

      const userData = buildUserData(data.user);
      if (!userData) {
        console.error('[AuthContext] login failed: buildUserData returned null', data.user);
        throw new Error('Invalid login response: could not build user');
      }

      // Create session
      const session = {
        user: userData,
        timestamp: new Date().toISOString(),
        lastValidatedAt: new Date().toISOString()
      };

      console.log('[AuthContext] login: about to setUser + localStorage + navigate');
      localStorage.setItem('auth_session', JSON.stringify(session));
      setUser(userData);
      toast.success('Welcome back!');
      navigate(redirectTo || '/');
      console.log('[AuthContext] login: setUser + localStorage + navigate completed');

      return userData;
    } catch (error) {
      console.error('[AuthContext] login failed:', error.message, error);
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
