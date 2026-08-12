import { useState, useEffect } from "react";
import { motion } from 'framer-motion';
import {
  Cog6ToothIcon,
  BellIcon,
  CheckCircleIcon,
  LockClosedIcon,
  EyeIcon,
  EyeSlashIcon,
  UsersIcon,
  KeyIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { useAuth } from '../contexts/AuthContext';
import UserManagement from '../components/UserManagement/UserManagement';
import { authFetch } from '../utils/authFetch';
import { errorMessage } from '../utils/apiValidate';

const Settings = () => {
  const { user, changePassword } = /** @type {AuthContextValue} */ (useAuth());
  const isLinasTenant = user?.tenantId === 'linas';
  const [activeTab, setActiveTab] = useState(isLinasTenant ? 'general' : 'security');
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: ''
  });
  const [showPasswords, setShowPasswords] = useState({
    current: false,
    new: false,
    confirm: false
  });
  const [settings, setSettings] = useState(/** @type {SettingsFormState} */ ({
    botName: 'Lina\'s Laser Bot',
    defaultLanguage: 'en',
    responseTimeout: 5,
    enableVoice: true,
    enableImages: true,
    enableTraining: true,
    notificationsEnabled: true,
    emailAlerts: true,
    humanTakeoverNotifyMobiles: '',
  }));
  useEffect(() => {
    if (!isLinasTenant && (activeTab === 'general' || activeTab === 'notifications')) {
      setActiveTab('security');
    }
  }, [activeTab, isLinasTenant]);

  // Load settings from API on mount and when page is shown/refreshed
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const res = await authFetch('/api/settings');
        const data = await res.json();
        if (data.success && data.settings) {
          const s = data.settings;
          const general = s.general || {};
          const notifications = s.notifications || {};
          const lang = String(general.defaultLanguage || 'en').toLowerCase();
          setSettings({
            botName: general.botName ?? 'Lina\'s Laser Bot',
            defaultLanguage: ['en', 'ar', 'fr'].includes(lang) ? lang : 'en',
            responseTimeout: general.responseTimeout ?? 5,
            enableVoice: general.enableVoice ?? true,
            enableImages: general.enableImages ?? true,
            enableTraining: general.enableTraining ?? true,
            notificationsEnabled: notifications.notificationsEnabled ?? true,
            emailAlerts: notifications.emailAlerts ?? true,
            humanTakeoverNotifyMobiles: notifications.humanTakeoverNotifyMobiles ?? '',
          });
        }
      } catch (e) {
        console.error('Error loading settings:', e);
      }
    };
    if (isLinasTenant) {
      loadSettings();
    }
  }, [isLinasTenant]);

  // Permission or explicit platform_owner — never role===admin alone.
  const canManageUsers =
    user?.resolvedPermissions?.userManagement === true ||
    user?.role === 'platform_owner';

  const tabs = [
    ...(isLinasTenant ? [{ id: 'general', name: 'General', icon: Cog6ToothIcon, color: 'from-blue-500 to-cyan-500' }] : []),
    { id: 'security', name: 'Security', icon: LockClosedIcon, color: 'from-red-500 to-pink-500' },
    ...(isLinasTenant ? [
      { id: 'notifications', name: 'Notifications', icon: BellIcon, color: 'from-orange-500 to-red-500' },
    ] : []),
    // Users tab only visible to users with userManagement permission
    ...(canManageUsers ? [{ id: 'users', name: 'Users', icon: UsersIcon, color: 'from-indigo-500 to-violet-500' }] : []),
  ];

  const systemLanguages = [
    { code: 'en', name: 'English' },
    { code: 'ar', name: 'Arabic' },
    { code: 'fr', name: 'French' },
  ];

  const handleSaveSettings = async () => {
    try {
      const lang = ['en', 'ar', 'fr'].includes(settings.defaultLanguage) ? settings.defaultLanguage : 'en';
      // System language only — bot identity / features live in AI Setup.
      const generalResponse = await authFetch('/api/settings/general', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          defaultLanguage: lang,
        })
      });

      if (generalResponse.ok) {
        toast.success('Settings saved successfully!');
      } else {
        toast.error('Failed to save settings');
      }
    } catch (error) {
      console.error('Error saving settings:', error);
      toast.error('Failed to save settings');
    }
  };

  const handleSaveNotificationSettings = async () => {
    try {
      const notificationResponse = await authFetch('/api/settings/notifications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          notificationsEnabled: settings.notificationsEnabled,
          emailAlerts: settings.emailAlerts,
        })
      });

      if (notificationResponse.ok) {
        toast.success('Notification settings saved successfully!');
      } else {
        toast.error('Failed to save notification settings');
      }
    } catch (error) {
      console.error('Error saving notification settings:', error);
      toast.error('Failed to save notification settings');
    }
  };

  /** @param {import('react').FormEvent<HTMLFormElement>} e */
  const handleChangePassword = async (e) => {
    e.preventDefault();

    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      toast.error('New passwords do not match');
      return;
    }

    if (passwordForm.newPassword.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }

    try {
      await changePassword(passwordForm.currentPassword, passwordForm.newPassword);
      setPasswordForm({
        currentPassword: '',
        newPassword: '',
        confirmPassword: ''
      });
      toast.success('Password changed successfully!');
    } catch (error) {
      toast.error(errorMessage(error) || 'Failed to change password');
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="text-center"
      >
        <h1 className="text-4xl font-bold gradient-text font-display mb-4">
          Settings & Configuration
        </h1>
        <p className="text-xl text-slate-600 max-w-2xl mx-auto">
          Manage system language, security, and notification preferences.
        </p>
      </motion.div>

      {/* Tabs */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="flex justify-center"
      >
        <div className="glass rounded-2xl p-2 inline-flex flex-wrap gap-2 justify-center">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative flex items-center space-x-2 px-6 py-3 rounded-xl font-medium transition-all duration-200 ${
                activeTab === tab.id
                  ? 'text-white shadow-lg'
                  : 'text-slate-600 hover:text-slate-800 hover:bg-white/50'
              }`}
            >
              {activeTab === tab.id && (
                <motion.div
                  layoutId="activeSettingsTab"
                  className={`absolute inset-0 bg-gradient-to-r ${tab.color} rounded-xl`}
                  transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                />
              )}
              <tab.icon className="w-5 h-5 relative z-10" />
              <span className="relative z-10">{tab.name}</span>
            </button>
          ))}
        </div>
      </motion.div>

      {/* Content */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.4 }}
        className="max-w-4xl mx-auto"
      >
        {activeTab === 'general' && (
          <div className="card">
            <h2 className="text-xl font-bold text-slate-800 font-display mb-6 flex items-center">
              <Cog6ToothIcon className="w-6 h-6 mr-2 text-blue-600" />
              General Settings
            </h2>

            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  System language
                </label>
                <p className="text-sm text-slate-600 mb-3">
                  Choose the dashboard system language (English, Arabic, or French). Bot content languages are managed in AI Setup.
                </p>
                <select
                  value={settings.defaultLanguage}
                  onChange={(e) => setSettings({...settings, defaultLanguage: e.target.value})}
                  className="input-field w-full max-w-md"
                >
                  {systemLanguages.map((lang) => (
                    <option key={lang.code} value={lang.code}>
                      {lang.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex justify-end">
                <button
                  onClick={handleSaveSettings}
                  className="btn-primary"
                >
                  <CheckCircleIcon className="w-5 h-5 inline mr-2" />
                  Save Changes
                </button>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'security' && (
          <div className="card">
            <h2 className="text-xl font-bold text-slate-800 font-display mb-6 flex items-center">
              <LockClosedIcon className="w-6 h-6 mr-2 text-red-600" />
              Security Settings
            </h2>

            <div className="space-y-6">
              {/* Account Information */}
              <div className="glass rounded-xl p-4">
                <h3 className="font-semibold text-slate-800 mb-3">Account Information</h3>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Email</span>
                    <span className="text-sm font-medium text-slate-800">{user?.email || ''}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Role</span>
                    <span className="text-sm font-medium text-slate-800 capitalize">{user?.role || 'Admin'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Account Created</span>
                    <span className="text-sm font-medium text-slate-800">
                      {user?.createdAt ? new Date(user.createdAt).toLocaleDateString() : 'N/A'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Change Password */}
              <div className="glass rounded-xl p-4">
                <h3 className="font-semibold text-slate-800 mb-3">Change Password</h3>
                <form onSubmit={handleChangePassword} className="space-y-4">
                  {/* Current Password */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Current Password
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <LockClosedIcon className="h-5 w-5 text-slate-400" />
                      </div>
                      <input
                        type={showPasswords.current ? 'text' : 'password'}
                        value={passwordForm.currentPassword}
                        onChange={(e) => setPasswordForm({...passwordForm, currentPassword: e.target.value})}
                        className="input-field pl-10 pr-10 w-full"
                        placeholder="Enter current password"
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPasswords({...showPasswords, current: !showPasswords.current})}
                        className="absolute inset-y-0 right-0 pr-3 flex items-center"
                      >
                        {showPasswords.current ? (
                          <EyeSlashIcon className="h-5 w-5 text-slate-400 hover:text-slate-600" />
                        ) : (
                          <EyeIcon className="h-5 w-5 text-slate-400 hover:text-slate-600" />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* New Password */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      New Password
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <LockClosedIcon className="h-5 w-5 text-slate-400" />
                      </div>
                      <input
                        type={showPasswords.new ? 'text' : 'password'}
                        value={passwordForm.newPassword}
                        onChange={(e) => setPasswordForm({...passwordForm, newPassword: e.target.value})}
                        className="input-field pl-10 pr-10 w-full"
                        placeholder="Enter new password"
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPasswords({...showPasswords, new: !showPasswords.new})}
                        className="absolute inset-y-0 right-0 pr-3 flex items-center"
                      >
                        {showPasswords.new ? (
                          <EyeSlashIcon className="h-5 w-5 text-slate-400 hover:text-slate-600" />
                        ) : (
                          <EyeIcon className="h-5 w-5 text-slate-400 hover:text-slate-600" />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Confirm New Password */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Confirm New Password
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <LockClosedIcon className="h-5 w-5 text-slate-400" />
                      </div>
                      <input
                        type={showPasswords.confirm ? 'text' : 'password'}
                        value={passwordForm.confirmPassword}
                        onChange={(e) => setPasswordForm({...passwordForm, confirmPassword: e.target.value})}
                        className="input-field pl-10 pr-10 w-full"
                        placeholder="Confirm new password"
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPasswords({...showPasswords, confirm: !showPasswords.confirm})}
                        className="absolute inset-y-0 right-0 pr-3 flex items-center"
                      >
                        {showPasswords.confirm ? (
                          <EyeSlashIcon className="h-5 w-5 text-slate-400 hover:text-slate-600" />
                        ) : (
                          <EyeIcon className="h-5 w-5 text-slate-400 hover:text-slate-600" />
                        )}
                      </button>
                    </div>
                    {passwordForm.confirmPassword && passwordForm.newPassword !== passwordForm.confirmPassword && (
                      <p className="mt-1 text-xs text-red-600">Passwords do not match</p>
                    )}
                  </div>

                  <button
                    type="submit"
                    className="btn-primary w-full"
                    disabled={!passwordForm.currentPassword || !passwordForm.newPassword || passwordForm.newPassword !== passwordForm.confirmPassword}
                  >
                    <KeyIcon className="w-4 h-4 mr-2" />
                    Change Password
                  </button>
                </form>
              </div>

              {/* Security Tips */}
              <div className="glass rounded-xl p-4 bg-red-50 border border-red-200">
                <div className="flex items-start space-x-3">
                  <ShieldCheckIcon className="w-5 h-5 text-red-600 mt-0.5" />
                  <div>
                    <h4 className="font-medium text-red-800">Security Tips</h4>
                    <ul className="text-sm text-red-700 mt-1 space-y-1">
                      <li>Use a strong password with at least 8 characters</li>
                      <li>Include uppercase, lowercase, numbers, and symbols</li>
                      <li>Never share your password with anyone</li>
                      <li>Change your password regularly</li>
                      <li>Session expires after 24 hours of inactivity</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'notifications' && (
          <div className="card">
            <h2 className="text-xl font-bold text-slate-800 font-display mb-6 flex items-center">
              <BellIcon className="w-6 h-6 mr-2 text-orange-600" />
              Notification Settings
            </h2>

            <div className="space-y-6">
              {[
                { key: 'notificationsEnabled', label: 'Enable Notifications', desc: 'Receive WhatsApp and system notifications' },
                { key: 'emailAlerts', label: 'Email Alerts', desc: 'Get important alerts via email' },
              ].map((setting) => (
                <div key={setting.key} className="flex items-center justify-between p-4 glass rounded-xl">
                  <div>
                    <h4 className="font-medium text-slate-800">{setting.label}</h4>
                    <p className="text-sm text-slate-600">{setting.desc}</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings[/** @type {'notificationsEnabled' | 'emailAlerts'} */ (setting.key)]}
                      onChange={(e) => setSettings({...settings, [setting.key]: e.target.checked})}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
                  </label>
                </div>
              ))}

              <div className="flex justify-end">
                <button
                  onClick={handleSaveNotificationSettings}
                  className="btn-primary"
                >
                  <CheckCircleIcon className="w-5 h-5 inline mr-2" />
                  Save Notification Settings
                </button>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'users' && canManageUsers && (
          <UserManagement />
        )}
      </motion.div>
    </div>
  );
};

export default Settings;
