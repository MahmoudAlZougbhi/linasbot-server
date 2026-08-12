import { motion } from 'framer-motion';
import {
  ShieldCheckIcon,
  LockClosedIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';
import { SYSTEM_ROLES, PERMISSION_KEYS } from '../../constants/permissions';

const PERMISSION_LABELS = {
  dashboard: 'Dashboard',
  liveChat: 'Live Chat',
  training: 'AI Training',
  testing: 'Testing Lab',
  analytics: 'Analytics',
  smartMessaging: 'Smart Messaging',
  settings: 'Settings',
  userManagement: 'User Management',
  contentManagers: 'AI Setup',
  contentPublish: 'Content Publish',
  activityFlow: 'Interaction Logs',
};

/** @param {{ role: RoleData }} props */
const RoleCard = ({ role }) => {
  /** @type {Record<string, boolean>} */
  const rolePermissions = role.permissions && !Array.isArray(role.permissions)
    ? role.permissions
    : {};

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-xl p-4"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-purple-100 text-purple-600">
            <ShieldCheckIcon className="w-5 h-5" />
          </div>
          <div>
            <h4 className="font-semibold text-slate-800 flex items-center">
              {role.name}
              <span className="ml-2 text-xs text-slate-500 flex items-center">
                <LockClosedIcon className="w-3 h-3 mr-1" />
                System
              </span>
            </h4>
            <p className="text-sm text-slate-500">{String(role.description || '')}</p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {PERMISSION_KEYS.map(key => (
          <span
            key={key}
            className={`inline-flex items-center px-2 py-1 text-xs rounded-full ${
              rolePermissions[key]
                ? 'bg-green-100 text-green-700'
                : 'bg-slate-100 text-slate-500'
            }`}
          >
            {rolePermissions[key] ? (
              <CheckCircleIcon className="w-3 h-3 mr-1" />
            ) : (
              <XCircleIcon className="w-3 h-3 mr-1" />
            )}
            {PERMISSION_LABELS[/** @type {keyof typeof PERMISSION_LABELS} */ (key)]}
          </span>
        ))}
      </div>
    </motion.div>
  );
};

const RoleManager = () => {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800">Roles</h3>
        <p className="text-sm text-slate-500">
          System roles define dashboard permissions for users.
        </p>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">
          System Roles
        </h4>
        <div className="space-y-3">
          {Object.values(SYSTEM_ROLES).map(role => (
            <RoleCard key={role.id} role={role} />
          ))}
        </div>
      </div>
    </div>
  );
};

export default RoleManager;
