import React from 'react';
import { motion } from 'framer-motion';
import {
  HomeIcon,
  ChatBubbleLeftRightIcon,
  ClockIcon,
  AcademicCapIcon,
  BeakerIcon,
  ChartBarIcon,
  BellIcon,
  Cog6ToothIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';

const PERMISSION_CONFIG = [
  {
    key: 'dashboard',
    name: 'Dashboard',
    description: 'View main dashboard and metrics',
    icon: HomeIcon,
    color: 'blue'
  },
  {
    key: 'liveChat',
    name: 'Live Chat',
    description: 'Monitor and participate in live conversations',
    icon: ChatBubbleLeftRightIcon,
    color: 'green'
  },
  {
    key: 'chatHistory',
    name: 'Chat History',
    description: 'View past conversation records',
    icon: ClockIcon,
    color: 'amber'
  },
  {
    key: 'training',
    name: 'AI Training',
    description: 'Train and configure the AI bot',
    icon: AcademicCapIcon,
    color: 'purple'
  },
  {
    key: 'testing',
    name: 'Testing Lab',
    description: 'Test bot responses and behavior',
    icon: BeakerIcon,
    color: 'cyan'
  },
  {
    key: 'analytics',
    name: 'Analytics',
    description: 'View analytics and reports',
    icon: ChartBarIcon,
    color: 'indigo'
  },
  {
    key: 'smartMessaging',
    name: 'Smart Messaging',
    description: 'Configure automated messaging',
    icon: BellIcon,
    color: 'orange'
  },
  {
    key: 'settings',
    name: 'Settings',
    description: 'Configure system settings',
    icon: Cog6ToothIcon,
    color: 'slate'
  },
  {
    key: 'userManagement',
    name: 'User Management',
    description: 'Manage users and permissions',
    icon: UsersIcon,
    color: 'red'
  }
];

const colorClasses = {
  blue: 'bg-blue-100 text-blue-600',
  green: 'bg-green-100 text-green-600',
  amber: 'bg-amber-100 text-amber-600',
  purple: 'bg-purple-100 text-purple-600',
  cyan: 'bg-cyan-100 text-cyan-600',
  indigo: 'bg-indigo-100 text-indigo-600',
  orange: 'bg-orange-100 text-orange-600',
  slate: 'bg-slate-100 text-slate-600',
  red: 'bg-red-100 text-red-600'
};

const PermissionMatrix = ({ permissions, onChange, disabled = false }) => {
  const handleToggle = (key) => {
    if (disabled) return;
    onChange(key, !permissions[key]);
  };

  return (
    <div className={`grid grid-cols-1 md:grid-cols-2 gap-3 ${disabled ? 'opacity-60' : ''}`}>
      {PERMISSION_CONFIG.map((perm, index) => {
        const IconComponent = perm.icon;
        const isEnabled = permissions[perm.key];

        return (
          <motion.div
            key={perm.key}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, delay: index * 0.03 }}
            onClick={() => handleToggle(perm.key)}
            className={`flex items-center justify-between p-3 rounded-xl border transition-all ${
              disabled
                ? 'cursor-not-allowed border-slate-200 bg-slate-50'
                : 'cursor-pointer hover:shadow-md'
            } ${
              isEnabled
                ? 'border-primary-200 bg-primary-50/50'
                : 'border-slate-200 bg-white'
            }`}
          >
            <div className="flex items-center space-x-3">
              <div className={`p-2 rounded-lg ${colorClasses[perm.color]}`}>
                <IconComponent className="w-4 h-4" />
              </div>
              <div>
                <p className="font-medium text-slate-800 text-sm">{perm.name}</p>
                <p className="text-xs text-slate-500">{perm.description}</p>
              </div>
            </div>

            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={isEnabled}
                onChange={() => handleToggle(perm.key)}
                disabled={disabled}
                className="sr-only peer"
              />
              <div className={`w-10 h-5 rounded-full peer transition-colors ${
                disabled
                  ? 'bg-slate-200'
                  : isEnabled
                    ? 'bg-primary-600'
                    : 'bg-slate-200'
              } peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300
                after:content-[''] after:absolute after:top-[2px] after:left-[2px]
                after:bg-white after:border-slate-300 after:border after:rounded-full
                after:h-4 after:w-4 after:transition-all ${
                isEnabled ? 'after:translate-x-5 after:border-white' : ''
              }`}></div>
            </label>
          </motion.div>
        );
      })}
    </div>
  );
};

export default PermissionMatrix;
