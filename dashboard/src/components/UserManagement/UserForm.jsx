import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  XMarkIcon,
  UserIcon,
  EnvelopeIcon,
  LockClosedIcon,
  ShieldCheckIcon,
  EyeIcon,
  EyeSlashIcon,
} from '@heroicons/react/24/outline';
import { SYSTEM_ROLES, DEFAULT_PERMISSIONS } from '../../constants/permissions';
import { getCustomRoles, resolveUserPermissions } from '../../utils/permissions';
import PermissionMatrix from './PermissionMatrix';

const UserForm = ({ user, onSubmit, onClose }) => {
  const isEditing = !!user;
  const allRoles = { ...SYSTEM_ROLES, ...getCustomRoles() };

  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    role: 'viewer',
    status: 'active',
    useCustomPermissions: false,
    permissions: { ...DEFAULT_PERMISSIONS }
  });

  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState({});

  // Initialize form with user data if editing
  useEffect(() => {
    if (user) {
      setFormData({
        name: user.name || '',
        email: user.email || '',
        password: '',
        role: user.role || 'viewer',
        status: user.status || 'active',
        useCustomPermissions: !!user.permissions,
        permissions: user.permissions || resolveUserPermissions(user)
      });
    }
  }, [user]);

  // Update permissions when role changes (if not using custom)
  useEffect(() => {
    if (!formData.useCustomPermissions) {
      const role = allRoles[formData.role];
      if (role) {
        setFormData(prev => ({
          ...prev,
          permissions: { ...role.permissions }
        }));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formData.role, formData.useCustomPermissions]);

  const validateForm = () => {
    const newErrors = {};

    if (!formData.name.trim()) {
      newErrors.name = 'Name is required';
    }

    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Invalid email format';
    }

    if (!isEditing && !formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password && formData.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateForm()) return;

    setSubmitting(true);
    try {
      const submitData = {
        name: formData.name,
        email: formData.email,
        role: formData.role,
        status: formData.status,
        permissions: formData.useCustomPermissions ? formData.permissions : null
      };

      // Only include password if provided
      if (formData.password) {
        submitData.password = formData.password;
      }

      await onSubmit(submitData);
    } catch (error) {
      // Error handling is done in parent
    } finally {
      setSubmitting(false);
    }
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
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="absolute inset-0 bg-black/50 backdrop-blur-sm"
          onClick={onClose}
        />

        {/* Modal */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto m-4 glass rounded-2xl shadow-2xl"
        >
          {/* Header */}
          <div className="sticky top-0 z-10 flex items-center justify-between p-6 border-b border-slate-200 bg-white/80 backdrop-blur-sm rounded-t-2xl">
            <h3 className="text-xl font-bold text-slate-800 font-display">
              {isEditing ? 'Edit User' : 'Create New User'}
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
              <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
                Basic Information
              </h4>

              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  Name
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <UserIcon className="h-5 w-5 text-slate-400" />
                  </div>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className={`input-field pl-10 w-full ${errors.name ? 'border-red-500' : ''}`}
                    placeholder="Enter full name"
                  />
                </div>
                {errors.name && <p className="mt-1 text-xs text-red-600">{errors.name}</p>}
              </div>

              {/* Email */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  Email
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <EnvelopeIcon className="h-5 w-5 text-slate-400" />
                  </div>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className={`input-field pl-10 w-full ${errors.email ? 'border-red-500' : ''}`}
                    placeholder="Enter email address"
                    disabled={isEditing}
                  />
                </div>
                {errors.email && <p className="mt-1 text-xs text-red-600">{errors.email}</p>}
              </div>

              {/* Password */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  {isEditing ? 'New Password (leave blank to keep current)' : 'Password'}
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <LockClosedIcon className="h-5 w-5 text-slate-400" />
                  </div>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    className={`input-field pl-10 pr-10 w-full ${errors.password ? 'border-red-500' : ''}`}
                    placeholder={isEditing ? 'Enter new password' : 'Enter password'}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center"
                  >
                    {showPassword ? (
                      <EyeSlashIcon className="h-5 w-5 text-slate-400 hover:text-slate-600" />
                    ) : (
                      <EyeIcon className="h-5 w-5 text-slate-400 hover:text-slate-600" />
                    )}
                  </button>
                </div>
                {errors.password && <p className="mt-1 text-xs text-red-600">{errors.password}</p>}
              </div>
            </div>

            {/* Role & Status */}
            <div className="space-y-4">
              <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
                Role & Status
              </h4>

              <div className="grid grid-cols-2 gap-4">
                {/* Role */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Role
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <ShieldCheckIcon className="h-5 w-5 text-slate-400" />
                    </div>
                    <select
                      value={formData.role}
                      onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                      className="input-field pl-10 w-full"
                    >
                      {Object.values(allRoles).map((role) => (
                        <option key={role.id} value={role.id}>
                          {role.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {allRoles[formData.role]?.description}
                  </p>
                </div>

                {/* Status */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Status
                  </label>
                  <select
                    value={formData.status}
                    onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                    className="input-field w-full"
                  >
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                    <option value="suspended">Suspended</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Custom Permissions */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
                  Permissions
                </h4>
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.useCustomPermissions}
                    onChange={(e) => setFormData({ ...formData, useCustomPermissions: e.target.checked })}
                    className="w-4 h-4 text-primary-600 border-slate-300 rounded focus:ring-primary-500"
                  />
                  <span className="text-sm text-slate-600">Use custom permissions</span>
                </label>
              </div>

              <PermissionMatrix
                permissions={formData.permissions}
                onChange={handlePermissionChange}
                disabled={!formData.useCustomPermissions}
              />

              {!formData.useCustomPermissions && (
                <p className="text-xs text-slate-500">
                  Permissions are inherited from the selected role. Enable custom permissions to override.
                </p>
              )}
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end space-x-3 pt-4 border-t border-slate-200">
              <button
                type="button"
                onClick={onClose}
                className="btn-ghost"
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn-primary"
                disabled={submitting}
              >
                {submitting ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    {isEditing ? 'Updating...' : 'Creating...'}
                  </>
                ) : (
                  isEditing ? 'Update User' : 'Create User'
                )}
              </button>
            </div>
          </form>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};

export default UserForm;
