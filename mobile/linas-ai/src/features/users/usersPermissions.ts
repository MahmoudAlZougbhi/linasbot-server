import type { PublicUser } from '../../api/types';

/** Exact keys from backend `PERMISSION_KEYS` / web `DEFAULT_PERMISSIONS`. */
export const PERMISSION_KEYS = [
  'dashboard',
  'liveChat',
  'training',
  'testing',
  'analytics',
  'smartMessaging',
  'settings',
  'userManagement',
  'contentManagers',
  'contentPublish',
  'activityFlow',
  'requests',
  'requestsManage',
  'requestsNotify',
  'requestsManualChat',
  'requestsSensitive',
] as const;

export type PermissionKey = (typeof PERMISSION_KEYS)[number];

export type PermissionMap = Record<PermissionKey, boolean>;

/** Tenant-assignable roles (matches `services/role_assignment.py`). */
export const ASSIGNABLE_ROLES = ['admin', 'operator', 'viewer'] as const;
export type AssignableRole = (typeof ASSIGNABLE_ROLES)[number];

export const ACCOUNT_STATUSES = ['active', 'inactive', 'suspended'] as const;
export type AccountStatus = (typeof ACCOUNT_STATUSES)[number];

export const DEFAULT_PERMISSIONS: PermissionMap = {
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
  activityFlow: false,
  requests: false,
  requestsManage: false,
  requestsNotify: false,
  requestsManualChat: false,
  requestsSensitive: false,
};

export const ROLE_PERMISSIONS: Record<AssignableRole, PermissionMap> = {
  admin: {
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
    activityFlow: true,
    requests: true,
    requestsManage: true,
    requestsNotify: true,
    requestsManualChat: true,
    requestsSensitive: true,
  },
  operator: {
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
    activityFlow: true,
    requests: true,
    requestsManage: true,
    requestsNotify: true,
    requestsManualChat: true,
    requestsSensitive: false,
  },
  viewer: {
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
    activityFlow: true,
    requests: false,
    requestsManage: false,
    requestsNotify: false,
    requestsManualChat: false,
    requestsSensitive: false,
  },
};

export function emptyPermissions(): PermissionMap {
  return { ...DEFAULT_PERMISSIONS };
}

export function permissionsForRole(role: string): PermissionMap {
  if (role === 'admin' || role === 'platform_owner') {
    return { ...ROLE_PERMISSIONS.admin };
  }
  if (role === 'operator') {
    return { ...ROLE_PERMISSIONS.operator };
  }
  return { ...ROLE_PERMISSIONS.viewer };
}

export function resolvePermissions(
  role: string | undefined,
  custom: Record<string, boolean> | null | undefined,
): PermissionMap {
  const base = permissionsForRole(role || 'viewer');
  if (role === 'admin' || role === 'platform_owner') {
    return { ...ROLE_PERMISSIONS.admin };
  }
  if (!custom) {
    return base;
  }
  const next = { ...base };
  for (const key of PERMISSION_KEYS) {
    if (typeof custom[key] === 'boolean') {
      next[key] = custom[key];
    }
  }
  return next;
}

/** Same gate as web Settings + AuthContext (admin or userManagement). */
export function canManageUsers(user: PublicUser | null | undefined): boolean {
  if (!user) return false;
  if (user.role === 'admin' || user.role === 'platform_owner') return true;
  const resolved = resolvePermissions(user.role, user.permissions ?? null);
  return resolved.userManagement === true;
}

export function isAssignableRole(role: string): boolean {
  if (role === 'platform_owner') return false;
  if ((ASSIGNABLE_ROLES as readonly string[]).includes(role)) return true;
  return /^[a-z][a-z0-9_-]{1,39}$/.test(role);
}

export function permissionsFromRecord(raw: Record<string, boolean> | null | undefined): PermissionMap {
  const next = emptyPermissions();
  if (!raw) return next;
  for (const key of PERMISSION_KEYS) {
    if (typeof raw[key] === 'boolean') next[key] = raw[key];
  }
  return next;
}
