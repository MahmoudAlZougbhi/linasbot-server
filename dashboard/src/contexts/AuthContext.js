import React, { createContext, useState, useContext, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';

const AuthContext = createContext({});

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  // Check for existing session on mount
  useEffect(() => {
    checkSession();
  }, []);

  const checkSession = () => {
    try {
      const session = localStorage.getItem('auth_session');
      if (session) {
        const sessionData = JSON.parse(session);
        const sessionTime = new Date(sessionData.timestamp);
        const now = new Date();
        const hoursDiff = (now - sessionTime) / (1000 * 60 * 60);
        
        // Check if session is less than 24 hours old
        if (hoursDiff < 24) {
          setUser(sessionData.user);
        } else {
          localStorage.removeItem('auth_session');
        }
      }
    } catch (error) {
      console.error('Session check failed:', error);
    } finally {
      setLoading(false);
    }
  };

  const login = async (email, password) => {
    try {
      // Read from local JSON file (in production, this would be an API call)
      const users = await fetchUsers();
      
      const user = users.find(u => u.email === email);
      
      if (!user) {
        throw new Error('User not found');
      }
      
      // Simple password check (in production, use proper hashing)
      if (user.password !== btoa(password)) { // Basic encoding for demo
        throw new Error('Invalid password');
      }
      
      const userData = {
        id: user.id,
        email: user.email,
        name: user.name || email.split('@')[0],
        role: user.role || 'admin'
      };
      
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
      toast.error(error.message || 'Login failed');
      throw error;
    }
  };

  const register = async (email, password) => {
    try {
      // Read existing users
      const users = await fetchUsers();
      
      // Check if user already exists
      if (users.find(u => u.email === email)) {
        throw new Error('Email already registered');
      }
      
      // Create new user
      const newUser = {
        id: Date.now().toString(),
        email: email,
        password: btoa(password), // Basic encoding for demo
        name: email.split('@')[0],
        role: 'admin',
        createdAt: new Date().toISOString()
      };
      
      // In production, this would save to backend
      // For demo, we'll just store in localStorage
      users.push(newUser);
      localStorage.setItem('users_db', JSON.stringify(users));
      
      toast.success('Registration successful! Please login.');
      navigate('/login');
      
      return newUser;
    } catch (error) {
      toast.error(error.message || 'Registration failed');
      throw error;
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
      
      const users = await fetchUsers();
      const userIndex = users.findIndex(u => u.id === user.id);
      
      if (userIndex === -1) throw new Error('User not found');
      
      // Verify current password
      if (users[userIndex].password !== btoa(currentPassword)) {
        throw new Error('Current password is incorrect');
      }
      
      // Update password
      users[userIndex].password = btoa(newPassword);
      localStorage.setItem('users_db', JSON.stringify(users));
      
      toast.success('Password changed successfully');
      return true;
    } catch (error) {
      toast.error(error.message || 'Failed to change password');
      throw error;
    }
  };

  const fetchUsers = async () => {
    try {
      // Try to get users from localStorage first
      const stored = localStorage.getItem('users_db');
      if (stored) {
        return JSON.parse(stored);
      }
      
      // Default admin user
      const defaultUsers = [
        {
          id: '1',
          email: 'admin@lina.com',
          password: btoa('admin123'), // Password: admin123
          name: 'Admin',
          role: 'admin',
          createdAt: new Date().toISOString()
        }
      ];
      
      localStorage.setItem('users_db', JSON.stringify(defaultUsers));
      return defaultUsers;
    } catch (error) {
      console.error('Failed to fetch users:', error);
      return [];
    }
  };

  const value = {
    user,
    login,
    register,
    logout,
    changePassword,
    loading
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};