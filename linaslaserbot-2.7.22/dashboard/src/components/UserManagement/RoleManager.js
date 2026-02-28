import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ShieldCheckIcon,
  PlusIcon,
  PencilIcon,
  TrashIcon,
  XMarkIcon,
  LockClosedIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { SYSTEM_ROLES, DEFAULT_PERMISSIONS, PERMISSION_KEYS } from '../../constants/permissions';
import {
  getCustomRoles,
  createCustomRole,
  updateCustomRole,
  deleteCustomRole
} from '../../utils/permissions';
import PermissionMatrix from './PermissionMatrix';

const PERMISSION_LABELS = {
  dashboard: 'Dashboard',
  liveChat: 'Live Chat',
  chatHistory: 'Chat History',
  training: 'AI Training',
  testing: 'Testing Lab',
  analytics: 'Analytics',
  smartMessaging: 'Smart Messaging',
  settings: 'Settings',
  userManagement: 'User Management'
};

const RoleManager = () => {
  const [customRoles, setCustomRoles] = useState({});
  const [showRoleForm, setShowRoleForm] = useState(false);
  const [editingRole, setEditingRole] = useState(null);

  useEffect(() => {
    loadCustomRoles();
  }, []);

  const loadCustomRoles = () => {
    setCustomRoles(getCustomRoles());
  };

  const handleCreateRole = (roleData) => {
    try {
      createCustomRole(roleData);
      toast.success('Role created successfully');
      setShowRoleForm(false);
      loadCustomRoles();
    } catch (error) {
      toast.error('Failed to create role');
    }
  };

  const handleUpdateRole = (roleId, updates) => {
    try {
      updateCustomRole(roleId, updates);
      toast.success('Role updated successfully');
      setShowRoleForm(false);
      setEditingRole(null);
      loadCustomRoles();
    } catch (error) {
      toast.error('Failed to update role');
    }
  };

  const handleDeleteRole = (roleId) => {
    if (!window.confirm('Are you sure you want to delete this role?')) {
      return;
    }

    try {
      deleteCustomRole(roleId);
      toast.success('Role deleted successfully');
      loadCustomRoles();
    } catch (error) {
      toast.error('Failed to delete role');
    }
  };

  const RoleCard = ({ role, isSystem }) => (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-xl p-4"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-3">
          <div className={`p-2 rounded-lg ${
            isSystem ? 'bg-purple-100 text-purple-600' : 'bg-blue-100 text-blue-600'
          }`}>
            <ShieldCheckIcon className="w-5 h-5" />
          </div>
          <div>
            <h4 className="font-semibold text-slate-800 flex items-center">
              {role.name}
              {isSystem && (
                <span className="ml-2 text-xs text-slate-500 flex items-center">
                  <LockClosedIcon className="w-3 h-3 mr-1" />
                  System
                </span>
              )}
            </h4>
            <p className="text-sm text-slate-500">{role.description}</p>
          </div>
        </div>

        {!isSystem && (
          <div className="flex items-center space-x-2">
            <button
              onClick={() => {
                setEditingRole(role);
                setShowRoleForm(true);
              }}
              className="p-2 text-slate-500 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
              title="Edit role"
            >
              <PencilIcon className="w-4 h-4" />
            </button>
            <button
              onClick={() => handleDeleteRole(role.id)}
              className="p-2 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
              title="Delete role"
            >
              <TrashIcon className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* Permission badges */}
      <div className="flex flex-wrap gap-2">
        {PERMISSION_KEYS.map(key => (
          <span
            key={key}
            className={`inline-flex items-center px-2 py-1 text-xs rounded-full ${
              role.permissions[key]
                ? 'bg-green-100 text-green-700'
                : 'bg-slate-100 text-slate-500'
            }`}
          >
            {role.permissions[key] ? (
              <CheckCircleIcon className="w-3 h-3 mr-1" />
            ) : (
              <XCircleIcon className="w-3 h-3 mr-1" />
            )}
            {PERMISSION_LABELS[key]}
          </span>
        ))}
      </div>
    </motion.div>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-slate-800">Roles</h3>
          <p className="text-sm text-slate-500">
            Manage system and custom roles
          </p>
        </div>
        <button
          onClick={() => {
            setEditingRole(null);
            setShowRoleForm(true);
          }}
          className="btn-primary flex items-center space-x-2"
        >
          <PlusIcon className="w-5 h-5" />
          <span>Add Custom Role</span>
        </button>
      </div>

      {/* System Roles */}
      <div>
        <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">
          System Roles
        </h4>
        <div className="space-y-3">
          {Object.values(SYSTEM_ROLES).map(role => (
            <RoleCard key={role.id} role={role} isSystem={true} />
          ))}
        </div>
      </div>

      {/* Custom Roles */}
      <div>
        <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">
          Custom Roles
        </h4>
        {Object.keys(customRoles).length === 0 ? (
          <div className="text-center py-8 glass rounded-xl">
            <ShieldCheckIcon className="w-10 h-10 mx-auto text-slate-400 mb-3" />
            <p className="text-slate-600">No custom roles yet</p>
            <p className="text-sm text-slate-500">Create a custom role to define specific permissions</p>
          </div>
        ) : (
          <div className="space-y-3">
            {Object.values(customRoles).map(role => (
              <RoleCard key={role.id} role={role} isSystem={false} />
            ))}
          </div>
        )}
      </div>

      {/* Role Form Modal */}
      <AnimatePresence>
        {showRoleForm && (
          <RoleFormModal
            role={editingRole}
            onSubmit={editingRole
              ? (data) => handleUpdateRole(editingRole.id, data)
              : handleCreateRole
            }
            onClose={() => {
              setShowRoleForm(false);
              setEditingRole(null);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
};

const RoleFormModal = ({ role, onSubmit, onClose }) => {
  const isEditing = !!role;
  const [formData, setFormData] = useState({
    name: role?.name || '',
    description: role?.description || '',
    permissions: role?.permissions || { ...DEFAULT_PERMISSIONS }
  });

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!formData.name.trim()) {
      toast.error('Role name is required');
      return;
    }

    onSubmit(formData);
  };

  const handlePermissionChange = (key, value) => {
    setFormData(prev => ({
      ...prev,
      permissions: {
        ...prev.permissions,
        [key]: value
      }
    }));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto m-4 glass rounded-2xl shadow-2xl"
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between p-6 border-b border-slate-200 bg-white/80 backdrop-blur-sm rounded-t-2xl">
          <h3 className="text-xl font-bold text-slate-800 font-display">
            {isEditing ? 'Edit Role' : 'Create Custom Role'}
          </h3>
          <button
            onClick={onClose}
            className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Basic Info */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Role Name
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="input-field w-full"
                placeholder="e.g., Support Agent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Description
              </label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="input-field w-full"
                placeholder="Brief description of the role"
              />
            </div>
          </div>

          {/* Permissions */}
          <div className="space-y-4">
            <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
              Permissions
            </h4>
            <PermissionMatrix
              permissions={formData.permissions}
              onChange={handlePermissionChange}
            />
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end space-x-3 pt-4 border-t border-slate-200">
            <button
              type="button"
              onClick={onClose}
              className="btn-ghost"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary"
            >
              {isEditing ? 'Update Role' : 'Create Role'}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
};

export default RoleManager;
