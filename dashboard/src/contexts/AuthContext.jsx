import { createContext, useState, useContext, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { errorMessage } from '../utils/apiValidate';
import {
  API_BASE,
  SESSION_VALIDATE_MIN_INTERVAL_MS,
  buildUserData,
  withAuthFetch,
} from './AuthContext.helpers';
import { createAuthUserManagement } from './AuthContext.users';

/** @type {import('react').Context<AuthContextValue | null>} */
const AuthContext = createContext(/** @type {AuthContextValue | null} */ (null));

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(/** @type {AuthUser | null} */ (null));
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const checkSession = useCallback(async () => {
    try {
      const session = localStorage.getItem('auth_session');
      if (session) {
        const sessionData = JSON.parse(session);
        const sessionTime = new Date(sessionData.timestamp);
        const now = new Date();
        const hoursDiff = (now.getTime() - sessionTime.getTime()) / (1000 * 60 * 60);
        const lastValidatedAt = sessionData.lastValidatedAt
          ? new Date(sessionData.lastValidatedAt)
          : null;
        const validatedRecently = lastValidatedAt
          ? (now.getTime() - lastValidatedAt.getTime()) < SESSION_VALIDATE_MIN_INTERVAL_MS
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
          const response = await fetch(`${API_BASE}/session`, withAuthFetch({
            signal: controller.signal
          }));
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
          const hoursDiff = (now.getTime() - sessionTime.getTime()) / (1000 * 60 * 60);
          if (hoursDiff < 24 && sessionData.user?.id) {
            const cachedUser = buildUserData(sessionData.user);
            if (cachedUser) {
              console.warn('[AuthContext] using cached session after checkSession failure');
              setUser(cachedUser);
              return;
            }
          }
        }
      } catch {
        // Ignore fallback parse errors and clear invalid session below.
      }
      localStorage.removeItem('auth_session');
    }
  }, []);

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
  }, [checkSession]);

  const TRANSIENT_AUTH_ERROR = 'Authentication service temporarily unavailable';

  const login = async (
    /** @type {string} */ email,
    /** @type {string} */ password,
    /** @type {string} */ redirectTo = '/app',
    /** @type {number} */ retryCount = 0
  ) => {
    const maxRetries = 2;
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);
      const response = await fetch(`${API_BASE}/login`, withAuthFetch({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email, password }),
        signal: controller.signal
      }));
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
      if (data.csrf_token) {
        localStorage.setItem('csrf_token', data.csrf_token);
      }
      localStorage.setItem('auth_session', JSON.stringify(session));
      setUser(userData);
      toast.success('Welcome back!');
      navigate(redirectTo || '/app');
      console.log('[AuthContext] login: setUser + localStorage + navigate completed');

      return userData;
    } catch (error) {
      const msg = error instanceof Error && error.name === 'AbortError'
        ? 'Connection timed out. Is the backend running on port 8003?'
        : (errorMessage(error) || 'Login failed');
      console.error('[AuthContext] login failed:', msg, error);
      toast.error(msg);
      throw new Error(msg);
    }
  };

  /**
   * Public company registration — creates an isolated tenant admin and signs in.
   * @param {{ businessName: string; email: string; password: string; name?: string }} payload
   */
  const register = async (payload) => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 20000);
      const response = await fetch(`${API_BASE}/register`, withAuthFetch({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          business_name: payload.businessName,
          email: payload.email,
          password: payload.password,
          name: payload.name || null,
        }),
        signal: controller.signal,
      }));
      clearTimeout(timeoutId);
      const data = await response.json();
      if (!data.success) {
        throw new Error(data.error || 'Registration failed');
      }
      if (!data.user || typeof data.user !== 'object') {
        throw new Error('Invalid registration response: missing user data');
      }
      const userData = buildUserData(data.user);
      if (!userData) {
        throw new Error('Invalid registration response: could not build user');
      }
      if (data.csrf_token) {
        localStorage.setItem('csrf_token', data.csrf_token);
      }
      localStorage.setItem(
        'auth_session',
        JSON.stringify({
          user: userData,
          timestamp: new Date().toISOString(),
          lastValidatedAt: new Date().toISOString(),
        })
      );
      setUser(userData);
      toast.success('Company account created');
      return userData;
    } catch (error) {
      const msg =
        error instanceof Error && error.name === 'AbortError'
          ? 'Connection timed out. Is the backend running on port 8003?'
          : errorMessage(error) || 'Registration failed';
      toast.error(msg);
      throw new Error(msg);
    }
  };

  const logout = async () => {
    try {
      await fetch(`${API_BASE}/logout`, withAuthFetch({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      }));
    } catch (error) {
      console.error('Logout request failed:', error);
    }
    localStorage.removeItem('auth_session');
    localStorage.removeItem('csrf_token');
    setUser(null);
    navigate('/login');
    toast.success('Logged out successfully');
  };

  const changePassword = async (
    /** @type {string} */ currentPassword,
    /** @type {string} */ newPassword
  ) => {
    try {
      if (!user) throw new Error('Not authenticated');

      const response = await fetch(`${API_BASE}/change-password`, withAuthFetch({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword
        })
      }));

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Failed to change password');
      }

      toast.success('Password changed successfully');
      return true;
    } catch (error) {
      toast.error(errorMessage(error) || 'Failed to change password');
      throw error;
    }
  };


  const {
    getUsers,
    createUser,
    updateUser,
    deleteUser,
    refreshUser,
  } = createAuthUserManagement({ user, setUser });

  const value = {
    user,
    login,
    register,
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
