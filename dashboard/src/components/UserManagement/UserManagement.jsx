import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  UsersIcon,
  ShieldCheckIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { useAuth } from '../../contexts/AuthContext';
import UserList from './UserList';
import UserForm from './UserForm';
import RoleManager from './RoleManager';

const UserManagement = () => {
  const { getUsers, createUser, updateUser, deleteUser, user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('users');
  const [showUserForm, setShowUserForm] = useState(false);
  const [editingUser, setEditingUser] = useState(null);

  // Load users on mount
  useEffect(() => {
    loadUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const userList = await getUsers();
      setUsers(userList);
    } catch (error) {
      toast.error('Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateUser = async (userData) => {
    try {
      await createUser(userData);
      toast.success('User created successfully');
      setShowUserForm(false);
      loadUsers();
    } catch (error) {
      toast.error(error.message || 'Failed to create user');
      throw error;
    }
  };

  const handleUpdateUser = async (userId, updates) => {
    try {
      await updateUser(userId, updates);
      toast.success('User updated successfully');
      setShowUserForm(false);
      setEditingUser(null);
      loadUsers();
    } catch (error) {
      toast.error(error.message || 'Failed to update user');
      throw error;
    }
  };

  const handleDeleteUser = async (userId) => {
    if (!window.confirm('Are you sure you want to delete this user?')) {
      return;
    }

    try {
      await deleteUser(userId);
      toast.success('User deleted successfully');
      loadUsers();
    } catch (error) {
      toast.error(error.message || 'Failed to delete user');
    }
  };

  const handleEditUser = (user) => {
    setEditingUser(user);
    setShowUserForm(true);
  };

  const handleCloseForm = () => {
    setShowUserForm(false);
    setEditingUser(null);
  };

  const tabs = [
    { id: 'users', name: 'Users', icon: UsersIcon, color: 'from-blue-500 to-cyan-500' },
    { id: 'roles', name: 'Roles', icon: ShieldCheckIcon, color: 'from-purple-500 to-pink-500' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 font-display">
            User Management
          </h2>
          <p className="text-slate-600">
            Manage users and their permissions
          </p>
        </div>

        {activeTab === 'users' && (
          <button
            onClick={() => setShowUserForm(true)}
            className="btn-primary flex items-center space-x-2"
          >
            <PlusIcon className="w-5 h-5" />
            <span>Add User</span>
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex space-x-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`relative flex items-center space-x-2 px-6 py-3 rounded-xl font-medium transition-all duration-200 ${
              activeTab === tab.id
                ? 'text-white shadow-lg'
                : 'text-slate-600 hover:text-slate-800 hover:bg-white/50 glass'
            }`}
          >
            {activeTab === tab.id && (
              <motion.div
                layoutId="activeUserTab"
                className={`absolute inset-0 bg-gradient-to-r ${tab.color} rounded-xl`}
                transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
              />
            )}
            <tab.icon className="w-5 h-5 relative z-10" />
            <span className="relative z-10">{tab.name}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="glass rounded-2xl p-6">
        {activeTab === 'users' && (
          <UserList
            users={users}
            currentUserId={currentUser?.id}
            loading={loading}
            onEdit={handleEditUser}
            onDelete={handleDeleteUser}
          />
        )}

        {activeTab === 'roles' && (
          <RoleManager />
        )}
      </div>

      {/* User Form Modal */}
      {showUserForm && (
        <UserForm
          user={editingUser}
          onSubmit={editingUser ?
            (data) => handleUpdateUser(editingUser.id, data) :
            handleCreateUser
          }
          onClose={handleCloseForm}
        />
      )}
    </div>
  );
};

export default UserManagement;
