import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import {
  Bars3Icon,
  BellIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
  KeyIcon,
  ChevronDownIcon,
  SignalIcon,
} from '@heroicons/react/24/outline';
import { useAuth } from '../../contexts/AuthContext';
import { useOperatorStatus } from '../../contexts/OperatorStatusContext';
import { buildDisplayLabel } from '../../utils/buildInfo';
import { getTimezoneName } from '../../utils/dateUtils';

/** @param {{ onMenuClick: () => void; botStatus?: unknown }} props */
const Header = ({ onMenuClick, botStatus: _botStatus }) => {
  const { operatorStatus, setOperatorStatus } = useOperatorStatus();
  const [showDropdown, setShowDropdown] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const dropdownRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const notificationsRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const appTimezone = getTimezoneName();

  // Notifications come from a real API when available — never invent fake Live events.
  const notifications = /** @type {Array<{ id: number; type: string; message: string; time: string; read: boolean }>} */ ([]);

  const unreadCount = notifications.filter(n => !n.read).length;

  const currentTime = new Intl.DateTimeFormat('en-US', {
    timeZone: appTimezone,
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date());

  const currentDate = new Intl.DateTimeFormat('en-US', {
    timeZone: appTimezone,
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(new Date());

  // Close dropdowns when clicking outside
  useEffect(() => {
    /** @param {MouseEvent} event */
    const handleClickOutside = (event) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (dropdownRef.current && !dropdownRef.current.contains(target)) {
        setShowDropdown(false);
      }
      if (notificationsRef.current && !notificationsRef.current.contains(target)) {
        setShowNotifications(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = () => {
    setShowDropdown(false);
    logout();
  };

  const handleChangePassword = () => {
    setShowDropdown(false);
    navigate('/settings');
  };

  const handleSettings = () => {
    setShowDropdown(false);
    navigate('/settings');
  };

  return (
    <div>
      {user && user.emailVerified === false && (
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-950">
          Verify your email to unlock full access.{' '}
          <button
            type="button"
            className="font-semibold underline"
            onClick={() => navigate('/verify-email')}
          >
            Verify now
          </button>
        </div>
      )}
    <header className="glass border-b border-white/20 px-6 py-4">
      <div className="flex items-center justify-between">
        {/* Left Section */}
        <div className="flex items-center space-x-4">
          <button
            onClick={onMenuClick}
            className="p-2 rounded-lg hover:bg-white/20 transition-colors lg:hidden"
          >
            <Bars3Icon className="w-6 h-6 text-slate-600" />
          </button>
          
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
            className="hidden sm:block"
          >
            <p className="text-sm text-slate-500">
              {currentDate} • {currentTime}
            </p>
            <p className="text-xs text-slate-400 mt-1">
              Build {buildDisplayLabel}
            </p>
          </motion.div>
        </div>

        {/* Right Section */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
          className="flex items-center space-x-4"
        >
          {/* Operator Status + Live - above notification icon */}
          <select
            value={operatorStatus}
            onChange={(e) => setOperatorStatus(e.target.value)}
            className="glass rounded-full px-4 py-2 text-sm font-medium text-slate-700 border-0"
          >
            <option value="available">🟢 Available</option>
            <option value="busy">🟡 Busy</option>
            <option value="away">🔴 Away</option>
          </select>
          <div className="flex items-center space-x-2 text-sm">
            <SignalIcon className="w-4 h-4 text-green-500 animate-pulse" />
            <span className="text-slate-600">Live</span>
          </div>
          {/* Notifications */}
          <div className="relative" ref={notificationsRef}>
            <button
              onClick={() => setShowNotifications(!showNotifications)}
              className="relative p-2 rounded-lg hover:bg-white/20 transition-colors group"
            >
              <BellIcon className="w-6 h-6 text-slate-600 group-hover:text-slate-800" />
              {unreadCount > 0 && (
                <div className="absolute -top-1 -right-1 w-3 h-3 bg-red-400 rounded-full border border-white animate-pulse"></div>
              )}
            </button>

            {/* Notifications Dropdown */}
            <AnimatePresence>
              {showNotifications && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.2 }}
                  className="absolute right-0 mt-2 w-80 glass rounded-xl shadow-xl overflow-hidden z-50"
                >
                  {/* Header */}
                  <div className="px-4 py-3 border-b border-white/20 flex items-center justify-between">
                    <p className="text-sm font-medium text-slate-800">Notifications</p>
                    {unreadCount > 0 && (
                      <span className="text-xs bg-red-100 text-red-600 px-2 py-0.5 rounded-full">
                        {unreadCount} new
                      </span>
                    )}
                  </div>

                  {/* Notifications List */}
                  <div className="max-h-80 overflow-y-auto">
                    {notifications.length > 0 ? (
                      notifications.map((notification) => (
                        <div
                          key={notification.id}
                          className={`px-4 py-3 border-b border-white/10 hover:bg-white/20 transition-colors cursor-pointer ${
                            !notification.read ? 'bg-primary-50/50' : ''
                          }`}
                        >
                          <div className="flex items-start space-x-3">
                            <div className={`w-2 h-2 mt-2 rounded-full flex-shrink-0 ${
                              notification.type === 'warning' ? 'bg-yellow-400' :
                              notification.type === 'success' ? 'bg-green-400' :
                              'bg-blue-400'
                            }`}></div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm text-slate-700">{notification.message}</p>
                              <p className="text-xs text-slate-500 mt-1">{notification.time}</p>
                            </div>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="px-4 py-8 text-center">
                        <BellIcon className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                        <p className="text-sm text-slate-500">No notifications</p>
                      </div>
                    )}
                  </div>

                  {/* Footer */}
                  {notifications.length > 0 && (
                    <div className="px-4 py-2 border-t border-white/20">
                      <button
                        onClick={() => {
                          setShowNotifications(false);
                          navigate('/settings');
                        }}
                        className="w-full text-center text-sm text-primary-600 hover:text-primary-700 font-medium"
                      >
                        View all notifications
                      </button>
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* User Profile with Dropdown */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setShowDropdown(!showDropdown)}
              className="flex items-center space-x-3 glass rounded-full pl-1 pr-4 py-1 hover:bg-white/20 transition-colors"
            >
              <div className="relative">
                <div className="w-8 h-8 bg-gradient-to-br from-primary-400 to-secondary-400 rounded-full flex items-center justify-center text-white font-bold">
                  {user?.name?.charAt(0).toUpperCase() || 'A'}
                </div>
                <div className="absolute -bottom-1 -right-1 w-3 h-3 bg-green-400 rounded-full border border-white"></div>
              </div>
              <div className="hidden sm:block text-left">
                <p className="text-sm font-medium text-slate-700">{user?.name || 'Admin'}</p>
                <p className="text-xs text-slate-500">{user?.email || ''}</p>
              </div>
              <ChevronDownIcon className={`w-4 h-4 text-slate-600 transition-transform ${
                showDropdown ? 'rotate-180' : ''
              }`} />
            </button>

            {/* Dropdown Menu */}
            <AnimatePresence>
              {showDropdown && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.2 }}
                  className="absolute right-0 mt-2 w-56 glass rounded-xl shadow-xl overflow-hidden z-50"
                >
                  {/* User Info */}
                  <div className="px-4 py-3 border-b border-white/20">
                    <p className="text-sm font-medium text-slate-800">{user?.name || 'Admin'}</p>
                    <p className="text-xs text-slate-500">{user?.email || ''}</p>
                  </div>

                  {/* Menu Items */}
                  <div className="py-2">
                    <button
                      onClick={handleSettings}
                      className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-white/20 transition-colors flex items-center space-x-3"
                    >
                      <Cog6ToothIcon className="w-4 h-4" />
                      <span>Settings</span>
                    </button>
                    
                    <button
                      onClick={handleChangePassword}
                      className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-white/20 transition-colors flex items-center space-x-3"
                    >
                      <KeyIcon className="w-4 h-4" />
                      <span>Change Password</span>
                    </button>
                    
                    <div className="border-t border-white/20 my-2"></div>
                    
                    <button
                      onClick={handleLogout}
                      className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 transition-colors flex items-center space-x-3"
                    >
                      <ArrowRightOnRectangleIcon className="w-4 h-4" />
                      <span>Logout</span>
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      </div>

    </header>
    </div>
  );
};

export default Header;