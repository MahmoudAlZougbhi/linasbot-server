// Feature definitions for the RBAC system
export const FEATURES = {
  DASHBOARD: {
    key: 'dashboard',
    path: '/',
    name: 'Dashboard',
    description: 'View main dashboard and metrics'
  },
  LIVE_CHAT: {
    key: 'liveChat',
    path: '/live-chat',
    name: 'Live Chat',
    description: 'Monitor and participate in live conversations'
  },
  CHAT_HISTORY: {
    key: 'chatHistory',
    path: '/chat-history',
    name: 'Chat History',
    description: 'View past conversation records'
  },
  TRAINING: {
    key: 'training',
    path: '/training',
    name: 'AI Training',
    description: 'Train and configure the AI bot'
  },
  TESTING: {
    key: 'testing',
    path: '/testing',
    name: 'Testing Lab',
    description: 'Test bot responses and behavior'
  },
  ANALYTICS: {
    key: 'analytics',
    path: '/analytics',
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
  }
};

// Path to permission key mapping
export const PATH_TO_PERMISSION = {
  '/': 'dashboard',
  '/live-chat': 'liveChat',
  '/chat-history': 'chatHistory',
  '/training': 'training',
  '/testing': 'testing',
  '/analytics': 'analytics',
  '/smart-messaging': 'smartMessaging',
  '/settings': 'settings',
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
      chatHistory: true,
      training: true,
      testing: true,
      analytics: true,
      smartMessaging: true,
      settings: true,
      userManagement: true
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
      chatHistory: true,
      training: false,
      testing: false,
      analytics: true,
      smartMessaging: true,
      settings: false,
      userManagement: false
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
      chatHistory: true,
      training: false,
      testing: false,
      analytics: true,
      smartMessaging: false,
      settings: false,
      userManagement: false
    }
  }
};

// Default permissions template (all false)
export const DEFAULT_PERMISSIONS = {
  dashboard: false,
  liveChat: false,
  chatHistory: false,
  training: false,
  testing: false,
  analytics: false,
  smartMessaging: false,
  settings: false,
  userManagement: false
};

// Permission keys array for iteration
export const PERMISSION_KEYS = Object.keys(DEFAULT_PERMISSIONS);

// Feature metadata for UI display
export const FEATURE_METADATA = Object.values(FEATURES).map(f => ({
  key: f.key,
  name: f.name,
  description: f.description
}));
