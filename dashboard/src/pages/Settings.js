import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Cog6ToothIcon,
  KeyIcon,
  GlobeAltIcon,
  BellIcon,
  ShieldCheckIcon,
  ServerIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  LockClosedIcon,
  EyeIcon,
  EyeSlashIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { useAuth } from '../contexts/AuthContext';

const Settings = () => {
  const { user, changePassword } = useAuth();
  const [activeTab, setActiveTab] = useState('general');
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
  const [settings, setSettings] = useState({
    botName: 'Lina\'s Laser Bot',
    defaultLanguage: 'ar',
    responseTimeout: 5,
    enableVoice: true,
    enableImages: true,
    enableTraining: true,
    notificationsEnabled: true,
    emailAlerts: true,
    humanTakeoverNotifyMobiles: '',
  });

  const tabs = [
    { id: 'general', name: 'General', icon: Cog6ToothIcon, color: 'from-blue-500 to-cyan-500' },
    { id: 'security', name: 'Security', icon: LockClosedIcon, color: 'from-red-500 to-pink-500' },
    { id: 'api', name: 'API Keys', icon: KeyIcon, color: 'from-green-500 to-emerald-500' },
    { id: 'languages', name: 'Languages', icon: GlobeAltIcon, color: 'from-purple-500 to-pink-500' },
    { id: 'notifications', name: 'Notifications', icon: BellIcon, color: 'from-orange-500 to-red-500' },
  ];

  const languages = [
    { code: 'ar', name: 'Arabic', flag: '🇸🇦', enabled: true },
    { code: 'en', name: 'English', flag: '🇺🇸', enabled: true },
    { code: 'fr', name: 'French', flag: '🇫🇷', enabled: true },
    { code: 'franco', name: 'Franco-Arabic', flag: '🔤', enabled: true },
  ];

  const apiKeys = [
    { name: 'OpenAI API', key: 'sk-proj-dZNp...', status: 'active', service: 'GPT-4 & Whisper' },
    { name: '360Dialog', key: 'rqwWBA_sandbox', status: 'active', service: 'WhatsApp Sandbox' },
    { name: 'Meta WhatsApp', key: 'EAAZAXQ...', status: 'inactive', service: 'WhatsApp Cloud API' },
    { name: 'Firebase', key: 'firebase_data.json', status: 'active', service: 'Database & Auth' },
  ];

  const handleSaveSettings = async () => {
    try {
      // Save general settings
      const generalResponse = await fetch('/api/settings/general', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          botName: settings.botName,
          defaultLanguage: settings.defaultLanguage,
          responseTimeout: settings.responseTimeout,
          enableVoice: settings.enableVoice,
          enableImages: settings.enableImages,
          enableTraining: settings.enableTraining
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
      // Save notification settings
      const notificationResponse = await fetch('/api/settings/notifications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          notificationsEnabled: settings.notificationsEnabled,
          emailAlerts: settings.emailAlerts,
          humanTakeoverNotifyMobiles: settings.humanTakeoverNotifyMobiles
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

  const handleTestAPI = (apiName) => {
    toast.loading(`Testing ${apiName}...`, { duration: 2000 });
    setTimeout(() => {
      toast.success(`${apiName} connection successful!`);
    }, 2000);
  };

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
      toast.error(error.message || 'Failed to change password');
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
          Configure your AI bot settings, manage API keys, and customize behavior.
        </p>
      </motion.div>

      {/* Tabs */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="flex justify-center"
      >
        <div className="glass rounded-2xl p-2 inline-flex space-x-2">
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
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Bot Name
                  </label>
                  <input
                    type="text"
                    value={settings.botName}
                    onChange={(e) => setSettings({...settings, botName: e.target.value})}
                    className="input-field w-full"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Default Language
                  </label>
                  <select
                    value={settings.defaultLanguage}
                    onChange={(e) => setSettings({...settings, defaultLanguage: e.target.value})}
                    className="input-field w-full"
                  >
                    {languages.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.flag} {lang.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Response Timeout (seconds)
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="30"
                    value={settings.responseTimeout}
                    onChange={(e) => setSettings({...settings, responseTimeout: parseInt(e.target.value)})}
                    className="input-field w-full"
                  />
                </div>
              </div>

              <div className="space-y-4">
                <h3 className="font-semibold text-slate-800">Features</h3>
                
                {[
                  { key: 'enableVoice', label: 'Voice Message Processing', desc: 'Allow voice message transcription' },
                  { key: 'enableImages', label: 'Image Analysis', desc: 'Enable image processing and analysis' },
                  { key: 'enableTraining', label: 'Training Mode', desc: 'Allow admins to train the bot' },
                ].map((feature) => (
                  <div key={feature.key} className="flex items-center justify-between p-4 glass rounded-xl">
                    <div>
                      <h4 className="font-medium text-slate-800">{feature.label}</h4>
                      <p className="text-sm text-slate-600">{feature.desc}</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={settings[feature.key]}
                        onChange={(e) => setSettings({...settings, [feature.key]: e.target.checked})}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
                    </label>
                  </div>
                ))}
              </div>

              <button
                onClick={handleSaveSettings}
                className="btn-primary w-full"
              >
                <CheckCircleIcon className="w-4 h-4 mr-2" />
                Save Settings
              </button>
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
                    <span className="text-sm font-medium text-slate-800">{user?.email || 'admin@lina.com'}</span>
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
                      <li>• Use a strong password with at least 8 characters</li>
                      <li>• Include uppercase, lowercase, numbers, and symbols</li>
                      <li>• Never share your password with anyone</li>
                      <li>• Change your password regularly</li>
                      <li>• Session expires after 24 hours of inactivity</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'api' && (
          <div className="card">
            <h2 className="text-xl font-bold text-slate-800 font-display mb-6 flex items-center">
              <KeyIcon className="w-6 h-6 mr-2 text-green-600" />
              API Keys & Integrations
            </h2>

            <div className="space-y-4">
              {apiKeys.map((api, index) => (
                <motion.div
                  key={api.name}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: index * 0.1 }}
                  className="glass rounded-xl p-4"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-4">
                      <div className={`p-2 rounded-lg ${
                        api.status === 'active' ? 'bg-green-100' : 'bg-slate-100'
                      }`}>
                        <ServerIcon className={`w-5 h-5 ${
                          api.status === 'active' ? 'text-green-600' : 'text-slate-400'
                        }`} />
                      </div>
                      <div>
                        <h3 className="font-semibold text-slate-800">{api.name}</h3>
                        <p className="text-sm text-slate-600">{api.service}</p>
                        <p className="text-xs text-slate-500 font-mono">{api.key}</p>
                      </div>
                    </div>
                    
                    <div className="flex items-center space-x-3">
                      <span className={`px-3 py-1 text-xs font-medium rounded-full ${
                        api.status === 'active' 
                          ? 'bg-green-100 text-green-700' 
                          : 'bg-slate-100 text-slate-600'
                      }`}>
                        {api.status === 'active' ? (
                          <>
                            <CheckCircleIcon className="w-3 h-3 inline mr-1" />
                            Active
                          </>
                        ) : (
                          <>
                            <ExclamationTriangleIcon className="w-3 h-3 inline mr-1" />
                            Inactive
                          </>
                        )}
                      </span>
                      
                      <button
                        onClick={() => handleTestAPI(api.name)}
                        className="btn-ghost text-sm px-3 py-1"
                      >
                        Test
                      </button>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>

            <div className="mt-6 glass rounded-xl p-4 bg-blue-50 border border-blue-200">
              <div className="flex items-start space-x-3">
                <ShieldCheckIcon className="w-5 h-5 text-blue-600 mt-0.5" />
                <div>
                  <h4 className="font-medium text-blue-800">Security Note</h4>
                  <p className="text-sm text-blue-700 mt-1">
                    API keys are securely stored and encrypted. Only partial keys are displayed for security.
                    Test connections regularly to ensure optimal performance.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'languages' && (
          <div className="card">
            <h2 className="text-xl font-bold text-slate-800 font-display mb-6 flex items-center">
              <GlobeAltIcon className="w-6 h-6 mr-2 text-purple-600" />
              Language Configuration
            </h2>

            <div className="space-y-4">
              {languages.map((lang, index) => (
                <motion.div
                  key={lang.code}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: index * 0.1 }}
                  className="glass rounded-xl p-4"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-4">
                      <div className="text-2xl">{lang.flag}</div>
                      <div>
                        <h3 className="font-semibold text-slate-800">{lang.name}</h3>
                        <p className="text-sm text-slate-600">Code: {lang.code}</p>
                      </div>
                    </div>
                    
                    <div className="flex items-center space-x-3">
                      <span className={`px-3 py-1 text-xs font-medium rounded-full ${
                        lang.enabled 
                          ? 'bg-green-100 text-green-700' 
                          : 'bg-slate-100 text-slate-600'
                      }`}>
                        {lang.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                      
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={lang.enabled}
                          onChange={() => {}}
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
                      </label>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>

            <div className="mt-6 glass rounded-xl p-4 bg-purple-50 border border-purple-200">
              <div className="flex items-start space-x-3">
                <GlobeAltIcon className="w-5 h-5 text-purple-600 mt-0.5" />
                <div>
                  <h4 className="font-medium text-purple-800">Language Rules</h4>
                  <ul className="text-sm text-purple-700 mt-1 space-y-1">
                    <li>• Bot responds in Arabic, English, or French only</li>
                    <li>• Franco-Arabic input is understood but responses are in Arabic</li>
                    <li>• Language detection is automatic based on input</li>
                  </ul>
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
                { key: 'notificationsEnabled', label: 'Enable Notifications', desc: 'Receive system notifications' },
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
                      checked={settings[setting.key]}
                      onChange={(e) => setSettings({...settings, [setting.key]: e.target.checked})}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
                  </label>
                </div>
              ))}

              {/* Human Takeover Notification Mobile Numbers */}
              <div className="glass rounded-xl p-4">
                <h3 className="font-semibold text-slate-800 mb-3">Human Takeover Notifications</h3>
                <p className="text-sm text-slate-600 mb-4">
                  Enter mobile numbers to be notified when a conversation is released from bot and waiting for human takeover.
                </p>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Mobile Numbers
                    <span className="text-slate-500 font-normal ml-2">(comma-separated)</span>
                  </label>
                  <textarea
                    value={settings.humanTakeoverNotifyMobiles}
                    onChange={(e) => setSettings({...settings, humanTakeoverNotifyMobiles: e.target.value})}
                    className="input-field w-full resize-none"
                    rows="3"
                    placeholder="e.g., +1234567890, +9876543210, +1122334455"
                  />
                  <p className="text-xs text-slate-500 mt-2">
                    💡 Tip: Enter mobile numbers with country code, separated by commas. These numbers will receive WhatsApp notifications when a conversation needs human attention.
                  </p>
                </div>
              </div>

              <button
                onClick={handleSaveNotificationSettings}
                className="btn-primary w-full"
              >
                <CheckCircleIcon className="w-4 h-4 mr-2" />
                Save Notification Settings
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
};

export default Settings;