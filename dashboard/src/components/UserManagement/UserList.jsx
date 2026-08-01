import React from 'react';
import { motion } from 'framer-motion';
import {
  PencilIcon,
  TrashIcon,
  UserCircleIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import { SYSTEM_ROLES } from '../../constants/permissions';
import { getCustomRoles } from '../../utils/permissions';

const UserList = ({ users, currentUserId, loading, onEdit, onDelete }) => {
  const allRoles = { ...SYSTEM_ROLES, ...getCustomRoles() };

  const getRoleName = (roleId) => {
    return allRoles[roleId]?.name || roleId;
  };

  const getStatusBadge = (status) => {
    const styles = {
      active: 'bg-green-100 text-green-700',
      inactive: 'bg-slate-100 text-slate-600',
      suspended: 'bg-red-100 text-red-700'
    };

    const icons = {
      active: <CheckCircleIcon className="w-3 h-3 mr-1" />,
      inactive: <XCircleIcon className="w-3 h-3 mr-1" />,
      suspended: <XCircleIcon className="w-3 h-3 mr-1" />
    };

    return (
      <span className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded-full ${styles[status] || styles.inactive}`}>
        {icons[status]}
        {status?.charAt(0).toUpperCase() + status?.slice(1)}
      </span>
    );
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (users.length === 0) {
    return (
      <div className="text-center py-12">
        <UserCircleIcon className="w-12 h-12 mx-auto text-slate-400 mb-4" />
        <p className="text-slate-600">No users found</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-slate-200">
            <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700">User</th>
            <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700">Role</th>
            <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700">Status</th>
            <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700">Last Login</th>
            <th className="text-right py-3 px-4 text-sm font-semibold text-slate-700">Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user, index) => (
            <motion.tr
              key={user.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: index * 0.05 }}
              className="border-b border-slate-100 hover:bg-slate-50/50 transition-colors"
            >
              <td className="py-4 px-4">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 bg-gradient-to-br from-primary-400 to-secondary-400 rounded-full flex items-center justify-center text-white font-semibold">
                    {user.name?.charAt(0).toUpperCase() || user.email?.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <p className="font-medium text-slate-800">
                      {user.name}
                      {user.id === currentUserId && (
                        <span className="ml-2 text-xs text-primary-600">(You)</span>
                      )}
                    </p>
                    <p className="text-sm text-slate-500">{user.email}</p>
                  </div>
                </div>
              </td>
              <td className="py-4 px-4">
                <span className={`inline-flex items-center px-3 py-1 text-xs font-medium rounded-full ${
                  user.role === 'admin'
                    ? 'bg-purple-100 text-purple-700'
                    : user.role === 'operator'
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-slate-100 text-slate-700'
                }`}>
                  {getRoleName(user.role)}
                </span>
                {user.permissions && (
                  <span className="ml-2 text-xs text-amber-600">Custom</span>
                )}
              </td>
              <td className="py-4 px-4">
                {getStatusBadge(user.status)}
              </td>
              <td className="py-4 px-4">
                <div className="flex items-center text-sm text-slate-600">
                  <ClockIcon className="w-4 h-4 mr-1" />
                  {formatDate(user.lastLogin)}
                </div>
              </td>
              <td className="py-4 px-4">
                <div className="flex items-center justify-end space-x-2">
                  <button
                    onClick={() => onEdit(user)}
                    className="p-2 text-slate-500 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                    title="Edit user"
                  >
                    <PencilIcon className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => onDelete(user.id)}
                    disabled={user.id === currentUserId}
                    className={`p-2 rounded-lg transition-colors ${
                      user.id === currentUserId
                        ? 'text-slate-300 cursor-not-allowed'
                        : 'text-slate-500 hover:text-red-600 hover:bg-red-50'
                    }`}
                    title={user.id === currentUserId ? "Cannot delete yourself" : "Delete user"}
                  >
                    <TrashIcon className="w-4 h-4" />
                  </button>
                </div>
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default UserList;
