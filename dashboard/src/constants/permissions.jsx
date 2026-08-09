// Feature definitions for the RBAC system
export const FEATURES = {
  DASHBOARD: {
    key: 'dashboard',
    path: '/app',
    name: 'Dashboard',
    description: 'View main dashboard and metrics'
  },
  LIVE_CHAT: {
    key: 'liveChat',
    path: '/live-chat',
    name: 'Live Chat',
    description: 'Monitor and participate in live conversations'
  },
  TRAINING: {
    key: 'training',
    path: '/training',
    name: 'FAQ (legacy redirect)',
    description: 'Legacy /training URL redirects to Content Managers → FAQ'
  },
  TESTING: {
    key: 'testing',
    path: '/testing',
    name: 'Testing Lab',
    description: 'Test bot responses and behavior'
  },
  ANALYTICS: {
    key: 'analytics',
    path: '/app',
    name: 'Analytics',
    description: 'View analytics and reports'
  },
  SMART_MESSAGING: {
    key: 'smartMessaging',
    path: '/smart-messaging',
    name: 'Smart Messaging',
    description: 'Configure automated messaging'
  },
  SETTINGS: {
    key: 'settings',
    path: '/settings',
    name: 'Settings',
    description: 'Configure system settings'
  },
  USER_MANAGEMENT: {
    key: 'userManagement',
    path: null,
    name: 'User Management',
    description: 'Manage users and permissions'
  },
  CONTENT_MANAGERS: {
    key: 'contentManagers',
    path: '/content-managers',
    name: 'Content Managers',
    description: 'Manage content files and knowledge content UI'
  },
  CONTENT_PUBLISH: {
    key: 'contentPublish',
    path: null,
    name: 'Content Publish',
    description: 'Publish and rollback Content Management versions'
  },
  ACTIVITY_FLOW: {
    key: 'activityFlow',
    path: '/activity-flow',
    name: 'Interaction Logs',
    description: 'Read-only observability of user ↔ bot ↔ AI turns'
  }
};

// Path to permission key mapping
export const PATH_TO_PERMISSION = {
  '/app': 'dashboard',
  '/live-chat': 'liveChat',
  '/mobile/live-chat': 'liveChat',
  '/training': 'contentManagers',
  '/testing': 'testing',
  '/analytics': 'dashboard',
  '/smart-messaging': 'smartMessaging',
  '/settings': 'settings',
  '/content-managers': 'contentManagers',
  '/activity-flow': 'activityFlow',
  '/api-debug': 'testing' // Debug route uses testing permission
};

// System role definitions with default permissions
export const SYSTEM_ROLES = {
  admin: {
    id: 'admin',
    name: 'Admin',
    description: 'Full access to all features',
    isSystem: true,
    permissions: {
      dashboard: true,
      liveChat: true,
      training: true,
      testing: true,
      analytics: true,
      smartMessaging: true,
      settings: true,
      userManagement: true,
      contentManagers: true,
      contentPublish: true,
      activityFlow: true
    }
  },
  platform_owner: {
    id: 'platform_owner',
    name: 'Platform Owner',
    description: 'Linas AI platform operator (CLI-provisioned only; not assignable in-app)',
    isSystem: true,
    assignableInTenantUi: false,
    permissions: {
      dashboard: true,
      liveChat: true,
      training: true,
      testing: true,
      analytics: true,
      smartMessaging: true,
      settings: true,
      userManagement: true,
      contentManagers: true,
      contentPublish: true,
      activityFlow: true
    }
  },
  operator: {
    id: 'operator',
    name: 'Operator',
    description: 'Can handle chats and view analytics',
    isSystem: true,
    permissions: {
      dashboard: true,
      liveChat: true,
      training: false,
      testing: false,
      analytics: true,
      smartMessaging: true,
      settings: false,
      userManagement: false,
      contentManagers: false,
      contentPublish: false,
      activityFlow: true
    }
  },
  viewer: {
    id: 'viewer',
    name: 'Viewer',
    description: 'Read-only access to dashboard and history',
    isSystem: true,
    permissions: {
      dashboard: true,
      liveChat: false,
      training: false,
      testing: false,
      analytics: true,
      smartMessaging: false,
      settings: false,
      userManagement: false,
      contentManagers: false,
      contentPublish: false,
      activityFlow: true
    }
  }
};

// Default permissions template (all false)
export const DEFAULT_PERMISSIONS = {
  dashboard: false,
  liveChat: false,
  training: false,
  testing: false,
  analytics: false,
  smartMessaging: false,
  settings: false,
  userManagement: false,
  contentManagers: false,
  contentPublish: false,
  activityFlow: false
};

// Permission keys array for iteration
export const PERMISSION_KEYS = Object.keys(DEFAULT_PERMISSIONS);

// Feature metadata for UI display
export const FEATURE_METADATA = Object.values(FEATURES).map(f => ({
  key: f.key,
  name: f.name,
  description: f.description
}));
