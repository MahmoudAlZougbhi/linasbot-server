import { useState, useEffect } from "react";
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
  UsersIcon,
  CalendarDaysIcon,
  CurrencyDollarIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import UserManagement from '../components/UserManagement/UserManagement';
import AiLimitsPanel from '../components/Settings/AiLimitsPanel';
import { authFetch } from '../utils/authFetch';
import { errorMessage } from '../utils/apiValidate';

const Settings = () => {
  const { user, changePassword } = /** @type {AuthContextValue} */ (useAuth());
  const isLinasTenant = (user?.tenantId || 'linas') === 'linas';
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
  const [settings, setSettings] = useState(/** @type {SettingsFormState} */ ({
    botName: 'Lina\'s Laser Bot',
    defaultLanguage: 'ar',
    responseTimeout: 5,
    enableVoice: true,
    enableImages: true,
    enableTraining: true,
    notificationsEnabled: true,
    emailAlerts: true,
    humanTakeoverNotifyMobiles: '',
  }));
  /** Branch holidays / closures for AI (pause booking + greetings) — saved under settings.clinic */
  const [branchHolidays, setBranchHolidays] = useState(/** @type {BranchHolidayRow[]} */ ([]));
  const [integrations, setIntegrations] = useState(/** @type {IntegrationStatus[]} */ ([]));
  const [integrationsError, setIntegrationsError] = useState(/** @type {string | null} */ (null));
  const [metaConnections, setMetaConnections] = useState(/** @type {MetaConnectionStatus[]} */ ([]));
  const [metaAuthorizations, setMetaAuthorizations] = useState(/** @type {MetaAuthorizationGroup[]} */ ([]));
  const [metaApps, setMetaApps] = useState(/** @type {MetaAppPublicStatus[]} */ ([]));
  const [metaRegistryEnabled, setMetaRegistryEnabled] = useState(false);
  const [metaInstagramLoginConfigured, setMetaInstagramLoginConfigured] = useState(false);
  const [metaInstagramLoginMissing, setMetaInstagramLoginMissing] = useState(/** @type {string[]} */ ([]));
  const [metaConnectionError, setMetaConnectionError] = useState(/** @type {string | null} */ (null));
  const [metaConnectionBusy, setMetaConnectionBusy] = useState('');
  const metaOAuthReady = metaApps.some(
    (item) => item.key === 'linas_first_party' && item.enabled && item.oauth_configured
  );
  const canStartMetaConnect = metaOAuthReady && metaConnectionBusy === '';
  const canStartInstagramLogin = metaInstagramLoginConfigured && metaConnectionBusy === '';

  useEffect(() => {
    if (!isLinasTenant && activeTab === 'general') {
      setActiveTab('wallet');
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
          setSettings({
            botName: general.botName ?? 'Lina\'s Laser Bot',
            defaultLanguage: general.defaultLanguage ?? 'ar',
            responseTimeout: general.responseTimeout ?? 5,
            enableVoice: general.enableVoice ?? true,
            enableImages: general.enableImages ?? true,
            enableTraining: general.enableTraining ?? true,
            notificationsEnabled: notifications.notificationsEnabled ?? true,
            emailAlerts: notifications.emailAlerts ?? true,
            humanTakeoverNotifyMobiles: notifications.humanTakeoverNotifyMobiles ?? '',
          });
          const clinic = s.clinic || {};
          setBranchHolidays(Array.isArray(clinic.branchHolidays) ? clinic.branchHolidays : []);
        }
      } catch (e) {
        console.error('Error loading settings:', e);
      }
    };
    const loadIntegrations = async () => {
      try {
        const res = await authFetch('/api/settings/integrations');
        const data = await res.json();
        if (!res.ok || !data.success) {
          setIntegrations([]);
          setIntegrationsError(data.error || `Failed to load integrations (${res.status})`);
          return;
        }
        setIntegrations(data.integrations || []);
        setIntegrationsError(null);
      } catch (e) {
        setIntegrations([]);
        setIntegrationsError(errorMessage(e) || 'Failed to load integrations');
      }
    };
    const loadMetaConnections = async () => {
      try {
        const res = await authFetch('/api/meta/connections');
        const data = await res.json();
        if (!res.ok || !data.success) {
          setMetaConnectionError(data.detail || data.error || `Failed to load Meta connections (${res.status})`);
          return;
        }
        setMetaConnections(Array.isArray(data.connections) ? data.connections : []);
        setMetaAuthorizations(Array.isArray(data.authorizations) ? data.authorizations : []);
        setMetaApps(Array.isArray(data.apps) ? data.apps : []);
        setMetaRegistryEnabled(data.registry_enabled === true);
        setMetaInstagramLoginConfigured(data.instagram_login_configured === true);
        setMetaInstagramLoginMissing(
          Array.isArray(data.instagram_login_config?.missing) ? data.instagram_login_config.missing : [],
        );
        setMetaConnectionError(null);
      } catch (e) {
        setMetaConnectionError(errorMessage(e) || 'Failed to load Meta connections');
      }
    };
    if (isLinasTenant) {
      loadSettings();
      loadIntegrations();
    }
    loadMetaConnections();
  }, [isLinasTenant]);

  // Check if user can manage users
  const canManageUsers = user?.role === 'admin' || user?.resolvedPermissions?.userManagement === true;

  const tabs = [
    ...(isLinasTenant ? [{ id: 'general', name: 'General', icon: Cog6ToothIcon, color: 'from-blue-500 to-cyan-500' }] : []),
    { id: 'wallet', name: 'Token Wallet', icon: CurrencyDollarIcon, color: 'from-emerald-500 to-teal-500' },
    { id: 'security', name: 'Security', icon: LockClosedIcon, color: 'from-red-500 to-pink-500' },
    { id: 'api', name: 'Integrations', icon: KeyIcon, color: 'from-green-500 to-emerald-500' },
    ...(isLinasTenant ? [
      { id: 'languages', name: 'Languages', icon: GlobeAltIcon, color: 'from-purple-500 to-pink-500' },
      { id: 'notifications', name: 'Notifications', icon: BellIcon, color: 'from-orange-500 to-red-500' },
    ] : []),
    // Users tab only visible to users with userManagement permission
    ...(canManageUsers ? [{ id: 'users', name: 'Users', icon: UsersIcon, color: 'from-indigo-500 to-violet-500' }] : []),
  ];

  const languages = [
    { code: 'ar', name: 'Arabic', flag: '🇸🇦', enabled: true },
    { code: 'en', name: 'English', flag: '🇺🇸', enabled: true },
    { code: 'fr', name: 'French', flag: '🇫🇷', enabled: true },
    { code: 'franco', name: 'Franco-Arabic', flag: '🔤', enabled: true },
  ];

  const handleSaveSettings = async () => {
    try {
      // Save general settings
      const generalResponse = await authFetch('/api/settings/general', {
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
      const notificationResponse = await authFetch('/api/settings/notifications', {
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

  const handleSaveClinicCalendar = async () => {
    try {
      const normalized = branchHolidays.map((row) => {
        let bid = row.branchId;
        if (bid === '' || bid === null || bid === undefined) bid = null;
        else bid = parseInt(String(bid), 10);
        const start = (row.startDate || '').trim();
        const end = (row.endDate || '').trim() || start;
        return {
          branchId: Number.isNaN(bid) ? null : bid,
          startDate: start,
          endDate: end,
          labelAr: (row.labelAr || '').trim(),
          labelEn: (row.labelEn || '').trim(),
          greetingAr: (row.greetingAr || '').trim(),
          greetingEn: (row.greetingEn || '').trim(),
          blockBooking: row.blockBooking !== false,
        };
      });
      const response = await authFetch('/api/settings/clinic', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ branchHolidays: normalized }),
      });
      if (response.ok) {
        toast.success('Clinic calendar saved — AI will use these holidays.');
      } else {
        toast.error('Failed to save clinic calendar');
      }
    } catch (error) {
      console.error('Error saving clinic calendar:', error);
      toast.error('Failed to save clinic calendar');
    }
  };

  const addHolidayRow = () => {
    setBranchHolidays((prev) => [
      ...prev,
      {
        branchId: '',
        startDate: '',
        endDate: '',
        labelAr: '',
        labelEn: '',
        greetingAr: '',
        greetingEn: '',
        blockBooking: true,
      },
    ]);
  };

  /** @param {string} apiName */
  const handleTestAPI = async (apiName) => {
    const toastId = toast.loading(`Checking ${apiName}...`);
    try {
      const res = await authFetch('/api/health');
      if (!res.ok) {
        toast.error(`${apiName}: health check failed (${res.status})`, { id: toastId });
        return;
      }
      const data = await res.json();
      if (data?.ok) {
        toast.success(`${apiName}: backend health OK (secrets not exposed)`, { id: toastId });
      } else {
        toast.error(`${apiName}: backend reported not ready`, { id: toastId });
      }
    } catch (e) {
      toast.error(`${apiName}: ${errorMessage(e) || 'connection failed'}`, { id: toastId });
    }
  };

  const handleConnectMeta = async () => {
    setMetaConnectionBusy('meta-oauth');
    try {
      const res = await authFetch('/api/meta/connections/start', {
        method: 'POST',
        body: JSON.stringify({ channel: 'unified' }),
      });
      const data = await res.json();
      if (!res.ok || !data.success || typeof data.authorization_url !== 'string') {
        throw new Error(data.detail || data.error || 'Meta connection could not be started');
      }
      const target = new URL(data.authorization_url);
      if (target.protocol !== 'https:' || target.hostname !== 'www.facebook.com') {
        throw new Error('Meta returned an invalid authorization destination');
      }
      window.location.assign(target.toString());
    } catch (e) {
      toast.error(errorMessage(e) || 'Meta connection could not be started');
      setMetaConnectionBusy('');
    }
  };

  const handleConnectInstagramLogin = async () => {
    setMetaConnectionBusy('instagram-login-oauth');
    try {
      const res = await authFetch('/api/meta/connections/instagram-login/start', {
        method: 'POST',
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok || !data.success || typeof data.authorization_url !== 'string') {
        throw new Error(data.detail || data.error || 'Instagram connection could not be started');
      }
      const target = new URL(data.authorization_url);
      if (target.protocol !== 'https:' || target.hostname !== 'www.instagram.com') {
        throw new Error('Instagram returned an invalid authorization destination');
      }
      window.location.assign(target.toString());
    } catch (e) {
      toast.error(errorMessage(e) || 'Instagram connection could not be started');
      setMetaConnectionBusy('');
    }
  };

  /** @param {MetaConnectionStatus} connection */
  const handleDisconnectMeta = async (connection) => {
    const assetLabel = connection.page_name
      || (connection.channel === 'instagram' ? connection.instagram_username : 'Facebook Page')
      || connection.channel;
    const confirmed = window.confirm(
      `Remove ${assetLabel} (${connection.asset_id_masked || 'asset'}) from Linas AI? `
      + 'Other connected Pages and Instagram accounts will stay active.',
    );
    if (!confirmed) {
      return;
    }
    setMetaConnectionBusy(connection.binding_id);
    try {
      const res = await authFetch(`/api/meta/connections/${connection.binding_id}/disconnect`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.error || 'Disconnect failed');
      }
      setMetaConnections((rows) => rows.map((row) => (
        row.binding_id === connection.binding_id ? { ...row, status: 'disconnected' } : row
      )));
      toast.success(`${connection.channel === 'facebook' ? 'Facebook' : 'Instagram'} disconnected`);
    } catch (e) {
      toast.error(errorMessage(e) || 'Disconnect failed');
    } finally {
      setMetaConnectionBusy('');
    }
  };

  /** @param {MetaConnectionStatus} connection */
  const handleReconnectMeta = async (connection) => {
    setMetaConnectionBusy(connection.binding_id);
    try {
      const res = await authFetch(`/api/meta/connections/${connection.binding_id}/reconnect`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.error || 'Reconnect failed');
      }
      setMetaConnections((rows) => rows.map((row) => (
        row.binding_id === connection.binding_id ? { ...row, status: 'active' } : row
      )));
      toast.success(`${connection.channel === 'facebook' ? 'Facebook' : 'Instagram'} reconnected`);
    } catch (e) {
      toast.error(errorMessage(e) || 'Reconnect failed');
    } finally {
      setMetaConnectionBusy('');
    }
  };

  /** @param {MetaConnectionStatus} connection */
  const handleActivateMeta = async (connection) => {
    setMetaConnectionBusy(connection.binding_id);
    try {
      const res = await authFetch(`/api/meta/connections/${connection.binding_id}/activate`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.error || 'Activation failed');
      }
      setMetaConnections((rows) => rows.map((row) => (
        row.binding_id === connection.binding_id ? { ...row, status: 'active' } : row
      )));
      toast.success(`${connection.channel === 'facebook' ? 'Facebook' : 'Instagram'} activated`);
    } catch (e) {
      toast.error(errorMessage(e) || 'Activation failed');
    } finally {
      setMetaConnectionBusy('');
    }
  };

  /** @param {number | undefined} unixSeconds */
  const formatConnectedAt = (unixSeconds) => {
    if (!unixSeconds) return '—';
    return new Date(unixSeconds * 1000).toLocaleString();
  };

  /**
   * @param {MetaConnectionStatus} connection
   * @param {boolean} enabled
   * @param {string} [instructions]
   */
  const handleUpdateCommentReplies = async (connection, enabled, instructions = '') => {
    setMetaConnectionBusy(`comment-${connection.binding_id}`);
    try {
      const res = await authFetch(`/api/meta/connections/${connection.binding_id}/comment-replies`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled, instructions }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.error || 'Comment reply settings could not be saved');
      }
      setMetaConnections((rows) => rows.map((row) => (
        row.binding_id === connection.binding_id
          ? { ...row, comment_replies: data.comment_replies }
          : row
      )));
      setMetaAuthorizations((groups) => groups.map((group) => ({
        ...group,
        assets: (group.assets || []).map((row) => (
          row.binding_id === connection.binding_id
            ? { ...row, comment_replies: data.comment_replies }
            : row
        )),
      })));
      toast.success(enabled ? 'AI comment replies enabled' : 'AI comment replies disabled');
    } catch (e) {
      toast.error(errorMessage(e) || 'Comment reply settings could not be saved');
    } finally {
      setMetaConnectionBusy('');
    }
  };

  /** @param {MetaConnectionStatus} connection */
  const renderMetaAssetRow = (connection) => {
    /** @type {NonNullable<MetaConnectionStatus['comment_replies']>} */
    const commentReplies = connection.comment_replies || { enabled: false, instructions: '' };
    const commentSwitchLabel = connection.channel === 'facebook'
      ? 'Enable AI replies to Facebook comments'
      : 'Enable AI replies to Instagram comments';
    const commentBusy = metaConnectionBusy === `comment-${connection.binding_id}`;
    const canConfigureComments = connection.app_key === 'linas_first_party' && connection.status === 'active';

    return (
    <div key={connection.binding_id} className="rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="font-medium text-slate-900">
            {connection.channel === 'facebook'
              ? (connection.page_name || 'Facebook Page')
              : (connection.auth_flow === 'instagram_login'
                ? (connection.instagram_username ? `@${connection.instagram_username}` : 'Instagram (Login)')
                : (connection.instagram_username ? `@${connection.instagram_username}` : 'Instagram account'))}
          </div>
          <div className="text-xs text-slate-500">
            {connection.channel === 'facebook'
              ? 'Facebook Page'
              : (connection.auth_flow === 'instagram_login' ? 'Instagram Login' : 'Instagram')}
            {' · '}
            ID {connection.asset_id_masked || '***'}
            {connection.page_id_masked && connection.channel === 'instagram'
              ? ` · Page ${connection.page_id_masked}`
              : ''}
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-slate-600">
            <span className="rounded-full bg-slate-100 px-2 py-0.5 capitalize">{connection.status}</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5">token {connection.token_status || 'unknown'}</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5">{connection.app_label || 'App A'}</span>
            <span>connected {formatConnectedAt(connection.connected_at || connection.created_at)}</span>
          </div>
        </div>
        <div className="flex gap-2">
          {connection.app_key === 'linas_first_party'
          && (connection.status === 'disconnected' || connection.status === 'inactive')
          && connection.token_status === 'valid' ? (
            <button
              type="button"
              className="btn-primary px-3 py-1 text-sm"
              disabled={metaConnectionBusy !== ''}
              onClick={() => handleReconnectMeta(connection)}
            >
              {metaConnectionBusy === connection.binding_id ? 'Reconnecting…' : 'Reconnect'}
            </button>
          ) : null}
          {connection.status === 'testing' && metaApps.some((item) => item.key === 'linas_first_party' && item.oauth_configured) ? (
            <button
              type="button"
              className="btn-primary px-3 py-1 text-sm"
              disabled={metaConnectionBusy !== ''}
              onClick={() => handleActivateMeta(connection)}
            >
              {metaConnectionBusy === connection.binding_id ? 'Activating…' : 'Activate'}
            </button>
          ) : null}
          {connection.status !== 'disconnected' ? (
            <button
              type="button"
              className="btn-ghost px-3 py-1 text-sm text-red-700"
              disabled={metaConnectionBusy !== ''}
              onClick={() => handleDisconnectMeta(connection)}
            >
              {metaConnectionBusy === connection.binding_id ? 'Working…' : 'Remove'}
            </button>
          ) : null}
        </div>
      </div>
      {canConfigureComments ? (
        <div className="mt-3 border-t border-slate-100 pt-3 space-y-3">
          <label className="flex items-center justify-between gap-3">
            <span className="text-sm text-slate-700">{commentSwitchLabel}</span>
            <button
              type="button"
              role="switch"
              aria-checked={Boolean(commentReplies.enabled)}
              disabled={commentBusy || metaConnectionBusy !== ''}
              onClick={() => handleUpdateCommentReplies(
                connection,
                !commentReplies.enabled,
                commentReplies.instructions || '',
              )}
              className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition ${
                commentReplies.enabled ? 'bg-primary-600' : 'bg-slate-200'
              } ${commentBusy ? 'opacity-60' : ''}`}
            >
              <span
                className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition ${
                  commentReplies.enabled ? 'translate-x-5' : 'translate-x-0.5'
                } mt-0.5`}
              />
            </button>
          </label>
          {!commentReplies.scopes_ready ? (
            <p className="text-xs text-amber-700">
              Re-authorize with Add / Manage Facebook &amp; Instagram after comment permissions are added to Login
              Configuration 1057282070324984.
            </p>
          ) : null}
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Comment reply instructions (optional)</label>
            <textarea
              rows={2}
              className="input-field w-full text-sm"
              placeholder="Short guidance for public comment replies"
              defaultValue={commentReplies.instructions || ''}
              disabled={commentBusy || metaConnectionBusy !== ''}
              onBlur={(e) => {
                const next = e.target.value.trim();
                if (next !== (commentReplies.instructions || '')) {
                  handleUpdateCommentReplies(connection, Boolean(commentReplies.enabled), next);
                }
              }}
            />
          </div>
        </div>
      ) : null}
    </div>
    );
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
        {activeTab === 'wallet' && (
          <div className="card space-y-4">
            <h2 className="text-xl font-bold text-slate-800 font-display flex items-center">
              <CurrencyDollarIcon className="w-6 h-6 mr-2 text-emerald-600" />
              Token Wallet
            </h2>
            <p className="text-sm text-slate-600">
              View remaining input and output AI tokens, buy recharge packs, and see spend analytics
              (Facebook vs Instagram, top chats). Detailed per-message cost lives in Interaction Logs.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                to="/wallet"
                className="inline-flex rounded-xl bg-gradient-to-r from-primary-600 to-secondary-600 px-4 py-2 text-sm font-semibold text-white"
              >
                Open Token Wallet
              </Link>
              <Link
                to="/activity-flow"
                className="inline-flex rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800"
              >
                Interaction Logs
              </Link>
            </div>
          </div>
        )}

        {activeTab === 'ai-limits' && (
          <div className="card">
            <AiLimitsPanel />
          </div>
        )}

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
                        checked={settings[/** @type {'enableVoice' | 'enableImages' | 'enableTraining'} */ (feature.key)]}
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

        {activeTab === 'api' && (
          <div className="card">
            <h2 className="text-xl font-bold text-slate-800 font-display mb-6 flex items-center">
              <KeyIcon className="w-6 h-6 mr-2 text-green-600" />
              Integration status (secrets are never displayed)
            </h2>

            {integrationsError ? (
              <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {integrationsError}
              </div>
            ) : null}

            <div className="mb-6 rounded-xl border border-blue-200 bg-blue-50 p-4">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <h3 className="font-semibold text-blue-900">Meta business messaging</h3>
                  <p className="mt-1 text-sm text-blue-800">
                    Connect Facebook Pages with Facebook Login for Business, or connect Instagram professional accounts directly with Instagram Login. Tokens stay encrypted on the server and are never shown here.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!canStartMetaConnect}
                    title={
                      canStartMetaConnect
                        ? 'Add or manage Facebook Pages and linked Instagram professional accounts using App A'
                        : 'Requires Facebook Login for Business on App A (META_APP_A_LOGIN_CONFIG_ID)'
                    }
                    onClick={() => handleConnectMeta()}
                  >
                    {metaConnectionBusy === 'meta-oauth' ? 'Opening Meta…' : 'Add / Manage Facebook & Instagram'}
                  </button>
                  <button
                    type="button"
                    className="btn-secondary text-sm disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!canStartInstagramLogin}
                    title={
                      canStartInstagramLogin
                        ? 'Connect an Instagram professional account with Instagram Login (no Facebook Page required)'
                        : `Requires Instagram Login configuration: ${metaInstagramLoginMissing.join(', ') || 'META_INSTAGRAM_LOGIN_APP_SECRET and META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN'}`
                    }
                    onClick={() => handleConnectInstagramLogin()}
                  >
                    {metaConnectionBusy === 'instagram-login-oauth' ? 'Opening Instagram…' : 'Connect Instagram'}
                  </button>
                </div>
              </div>
              {metaConnectionError ? (
                <p className="mt-3 text-sm text-red-700">{metaConnectionError}</p>
              ) : null}
              {!metaRegistryEnabled ? (
                <p className="mt-3 text-xs text-blue-700">Multi-app onboarding is staged but not enabled on this deployment.</p>
              ) : null}
              {metaRegistryEnabled && !metaInstagramLoginConfigured ? (
                <p className="mt-3 text-xs text-amber-800">
                  Connect Instagram is disabled until ops configure{' '}
                  <code className="font-mono">META_INSTAGRAM_LOGIN_APP_SECRET</code> and{' '}
                  <code className="font-mono">META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN</code>
                  {metaInstagramLoginMissing.length > 0 ? ` (missing: ${metaInstagramLoginMissing.join(', ')})` : ''}.
                </p>
              ) : null}
              {metaRegistryEnabled && !metaOAuthReady ? (
                <p className="mt-3 text-xs text-amber-800">
                  Add / Manage Facebook &amp; Instagram is disabled because Facebook Login for Business is not configured
                  for your Meta app on this server (missing <code className="font-mono">META_APP_A_LOGIN_CONFIG_ID</code>).
                  Lina uses one Meta app only — ask ops to add the Login configuration ID from the Meta Developer
                  console, then use Add / Manage below.
                </p>
              ) : null}
              {(metaAuthorizations.length > 0 || metaConnections.length > 0) ? (
                <div className="mt-4 space-y-4">
                  {(metaAuthorizations.length > 0 ? metaAuthorizations : [{ authorized_meta_user_id_hash: '', app_key: 'linas_first_party', app_label: 'Lina Meta app', authorization_title: 'Meta authorization — App A', assets: metaConnections }]).map((authorization) => (
                    <div key={authorization.authorized_meta_user_id_hash || authorization.authorization_title || 'meta-auth'} className="rounded-xl border border-slate-200 bg-slate-50/80 p-3">
                      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <div className="text-sm font-semibold text-slate-900">
                            {authorization.authorization_title
                              || (authorization.app_key === 'linas_first_party'
                                ? 'Meta authorization — App A'
                                : 'Connected through Linas AI')}
                          </div>
                          <div className="text-xs text-slate-500">
                            {authorization.app_label || 'Lina Meta app'}
                            {authorization.authorized_meta_user_id_hash
                              ? ` · auth ${authorization.authorized_meta_user_id_hash.slice(0, 8)}…`
                              : ''}
                          </div>
                        </div>
                      </div>
                      <div className="space-y-2">
                        {(authorization.assets || []).map((connection) => renderMetaAssetRow(connection))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            {isLinasTenant ? <div className="space-y-4">
              {integrations.map((api, index) => (
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
                        api.configured ? 'bg-green-100' : 'bg-slate-100'
                      }`}>
                        <ServerIcon className={`w-5 h-5 ${
                          api.configured ? 'text-green-600' : 'text-slate-400'
                        }`} />
                      </div>
                      <div>
                        <h3 className="font-semibold text-slate-800">{api.name}</h3>
                        <p className="text-sm text-slate-600">{api.service}</p>
                        <p className="text-xs text-slate-500">{api.notes}</p>
                      </div>
                    </div>

                    <div className="flex items-center space-x-3">
                      <span className={`px-3 py-1 text-xs font-medium rounded-full ${
                        api.configured
                          ? 'bg-green-100 text-green-700'
                          : 'bg-amber-100 text-amber-700'
                      }`}>
                        {api.configured ? (
                          <>
                            <CheckCircleIcon className="w-3 h-3 inline mr-1" />
                            Configured
                          </>
                        ) : (
                          <>
                            <ExclamationTriangleIcon className="w-3 h-3 inline mr-1" />
                            Missing env
                          </>
                        )}
                      </span>

                      <button
                        onClick={() => handleTestAPI(api.name)}
                        className="btn-ghost text-sm px-3 py-1"
                      >
                        Health check
                      </button>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div> : null}

            <div className="mt-6 glass rounded-xl p-4 bg-blue-50 border border-blue-200">
              <div className="flex items-start space-x-3">
                <ShieldCheckIcon className="w-5 h-5 text-blue-600 mt-0.5" />
                <div>
                  <h4 className="font-medium text-blue-800">Security Note</h4>
                  <p className="text-sm text-blue-700 mt-1">
                    Secrets are never displayed in the dashboard. Status reflects whether
                    required environment variables are present on the server.
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

                      <span className="text-xs text-slate-500">Managed by bot language detection</span>
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
                    <li>Bot responds in Arabic, English, or French only</li>
                    <li>Franco-Arabic input is understood but responses are in Arabic</li>
                    <li>Language detection is automatic based on input</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'clinic' && (
          <div className="card">
            <h2 className="text-xl font-bold text-slate-800 font-display mb-2 flex items-center">
              <CalendarDaysIcon className="w-6 h-6 mr-2 text-teal-600" />
              Clinic calendar — holidays & closures
            </h2>
            <p className="text-sm text-slate-600 mb-6 max-w-3xl leading-relaxed">
              Holidays and closure days per branch (or all branches). The AI reads this in every chat: if the customer asks for an appointment on a blocked day, it will not confirm booking for that day,
              explains politely, and can use the greeting you set. Use <strong>block booking</strong> when the branch is fully closed for that date range.
            </p>

            <div className="space-y-4">
              {branchHolidays.length === 0 && (
                <p className="text-sm text-slate-500 italic">No rows yet — add one for New Year, Eid, etc.</p>
              )}
              {branchHolidays.map((row, idx) => (
                <div key={idx} className="glass rounded-xl p-4 border border-teal-100 space-y-3">
                  <div className="flex flex-wrap gap-3 items-end">
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Branch</label>
                      <select
                        className="input-field text-sm"
                        value={row.branchId === null || row.branchId === undefined ? '' : String(row.branchId)}
                        onChange={(e) => {
                          const v = e.target.value;
                          const next = [...branchHolidays];
                          next[idx] = { ...next[idx], branchId: v === '' ? '' : v };
                          setBranchHolidays(next);
                        }}
                      >
                        <option value="">All branches</option>
                        <option value="1">Branch 1 (Beirut — CRM id 1)</option>
                        <option value="2">Branch 2 (Antelias — CRM id 2)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Start date</label>
                      <input
                        type="date"
                        className="input-field text-sm"
                        value={row.startDate || ''}
                        onChange={(e) => {
                          const next = [...branchHolidays];
                          next[idx] = { ...next[idx], startDate: e.target.value };
                          setBranchHolidays(next);
                        }}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">End date (optional)</label>
                      <input
                        type="date"
                        className="input-field text-sm"
                        value={row.endDate || ''}
                        onChange={(e) => {
                          const next = [...branchHolidays];
                          next[idx] = { ...next[idx], endDate: e.target.value };
                          setBranchHolidays(next);
                        }}
                      />
                    </div>
                    <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={row.blockBooking !== false}
                        onChange={(e) => {
                          const next = [...branchHolidays];
                          next[idx] = { ...next[idx], blockBooking: e.target.checked };
                          setBranchHolidays(next);
                        }}
                      />
                      Block booking
                    </label>
                    <button
                      type="button"
                      className="text-sm text-red-600 hover:underline ml-auto"
                      onClick={() => setBranchHolidays((prev) => prev.filter((_, i) => i !== idx))}
                    >
                      Remove
                    </button>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Label (Arabic)</label>
                      <input
                        className="input-field text-sm w-full"
                        dir="rtl"
                        placeholder="e.g. Eid al-Adha (Arabic label)"
                        value={row.labelAr || ''}
                        onChange={(e) => {
                          const next = [...branchHolidays];
                          next[idx] = { ...next[idx], labelAr: e.target.value };
                          setBranchHolidays(next);
                        }}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Label (EN)</label>
                      <input
                        className="input-field text-sm w-full"
                        placeholder="e.g. Eid al-Adha"
                        value={row.labelEn || ''}
                        onChange={(e) => {
                          const next = [...branchHolidays];
                          next[idx] = { ...next[idx], labelEn: e.target.value };
                          setBranchHolidays(next);
                        }}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Greeting (Arabic)</label>
                      <input
                        className="input-field text-sm w-full"
                        dir="rtl"
                        placeholder="Short greeting shown to customers (Arabic)"
                        value={row.greetingAr || ''}
                        onChange={(e) => {
                          const next = [...branchHolidays];
                          next[idx] = { ...next[idx], greetingAr: e.target.value };
                          setBranchHolidays(next);
                        }}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Greeting (EN)</label>
                      <input
                        className="input-field text-sm w-full"
                        placeholder="Eid Mubarak!"
                        value={row.greetingEn || ''}
                        onChange={(e) => {
                          const next = [...branchHolidays];
                          next[idx] = { ...next[idx], greetingEn: e.target.value };
                          setBranchHolidays(next);
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))}

              <div className="flex flex-wrap gap-3">
                <button type="button" onClick={addHolidayRow} className="btn-ghost text-sm px-4 py-2 border border-teal-200">
                  + Add holiday
                </button>
                <button type="button" onClick={handleSaveClinicCalendar} className="btn-primary text-sm px-6 py-2">
                  <CheckCircleIcon className="w-4 h-4 inline mr-2" />
                  Save clinic calendar
                </button>
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
                      checked={settings[/** @type {'notificationsEnabled' | 'emailAlerts'} */ (setting.key)]}
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
                    rows={3}
                    placeholder="e.g., +1234567890, +9876543210, +1122334455"
                  />
                  <p className="text-xs text-slate-500 mt-2">
                    Enter mobile numbers with country code, separated by commas. These numbers will receive WhatsApp notifications when a conversation needs human attention.
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

        {activeTab === 'users' && canManageUsers && (
          <UserManagement />
        )}
      </motion.div>
    </div>
  );
};

export default Settings;
