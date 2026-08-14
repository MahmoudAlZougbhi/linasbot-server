import type { StringKey } from '../../i18n/locales/en';

import {
  PERMISSION_KEYS,
  permissionsForRole,
  resolvePermissions,
  type PermissionKey,
  type PermissionMap,
} from './usersPermissions';

export type AccessScreenId =
  | 'dashboard'
  | 'liveChat'
  | 'requests'
  | 'aiSetup'
  | 'smartAnswers'
  | 'smartFollowUp'
  | 'integrations'
  | 'users'
  | 'subscription'
  | 'settings';

export type AccessScreen = {
  id: AccessScreenId;
  labelKey: StringKey;
  view: PermissionKey[];
  manage: PermissionKey[];
  /** Include in the list-row summary when view is granted. */
  summary: boolean;
};

/**
 * View/Manage rows → existing RBAC keys (no new permission flags).
 * Screens that share keys stay in sync by design.
 */
export const ACCESS_SCREENS: AccessScreen[] = [
  { id: 'dashboard', labelKey: 'usersAccessDashboard', view: ['dashboard'], manage: ['analytics'], summary: true },
  { id: 'liveChat', labelKey: 'usersAccessLiveChat', view: ['liveChat'], manage: ['liveChat'], summary: true },
  {
    id: 'requests',
    labelKey: 'usersAccessRequests',
    view: ['requests'],
    manage: ['requestsManage', 'requestsNotify', 'requestsManualChat'],
    summary: true,
  },
  {
    id: 'aiSetup',
    labelKey: 'usersAccessAiSetup',
    view: ['contentManagers'],
    manage: ['contentPublish'],
    summary: true,
  },
  {
    id: 'smartAnswers',
    labelKey: 'usersAccessSmartAnswers',
    view: ['contentManagers'],
    manage: ['contentPublish'],
    summary: false,
  },
  {
    id: 'smartFollowUp',
    labelKey: 'usersAccessSmartFollowUp',
    view: ['contentManagers'],
    manage: ['contentPublish'],
    summary: false,
  },
  { id: 'integrations', labelKey: 'usersAccessIntegrations', view: ['settings'], manage: ['settings'], summary: false },
  { id: 'users', labelKey: 'usersAccessUsers', view: ['userManagement'], manage: ['userManagement'], summary: true },
  {
    id: 'subscription',
    labelKey: 'usersAccessSubscription',
    view: ['settings'],
    manage: ['settings'],
    summary: false,
  },
  { id: 'settings', labelKey: 'usersAccessSettings', view: ['settings'], manage: ['settings'], summary: true },
];

export function accessViewChecked(screen: AccessScreen, perms: PermissionMap): boolean {
  return screen.view.every((key) => perms[key] === true);
}

export function accessManageChecked(screen: AccessScreen, perms: PermissionMap): boolean {
  return screen.manage.every((key) => perms[key] === true);
}

export function setAccessColumn(
  perms: PermissionMap,
  screen: AccessScreen,
  column: 'view' | 'manage',
  value: boolean,
): PermissionMap {
  const next: PermissionMap = { ...perms };
  const keys = column === 'view' ? screen.view : screen.manage;
  for (const key of keys) next[key] = value;
  if (column === 'manage' && value) {
    for (const key of screen.view) next[key] = true;
  }
  if (column === 'view' && !value) {
    for (const key of screen.manage) next[key] = false;
  }
  return next;
}

export function isFullAccess(perms: PermissionMap): boolean {
  return PERMISSION_KEYS.every((key) => perms[key] === true);
}

export function accessSummaryKeys(perms: PermissionMap): StringKey[] {
  if (isFullAccess(perms)) return ['usersFullAccess'];
  return ACCESS_SCREENS.filter((screen) => screen.summary && accessViewChecked(screen, perms)).map(
    (screen) => screen.labelKey,
  );
}

export function userInitials(name: string, email: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0].charAt(0)}${parts[1].charAt(0)}`.toUpperCase();
  }
  if (parts.length === 1 && parts[0].length >= 2) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  const local = (email.split('@')[0] || 'U').replace(/[^a-zA-Z]/g, '');
  if (local.length >= 2) return local.slice(0, 2).toUpperCase();
  return (local.charAt(0) || 'U').toUpperCase();
}

export function generateTempPassword(): string {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';
  const bytes = new Uint8Array(12);
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  return Array.from(bytes, (b) => chars[b % chars.length]).join('');
}

export function mapsEqual(a: PermissionMap, b: PermissionMap): boolean {
  return PERMISSION_KEYS.every((key) => a[key] === b[key]);
}

export function displayPermissions(
  role: string,
  custom: Record<string, boolean> | null | undefined,
  catalogPerms: Record<string, boolean> | null | undefined,
): PermissionMap {
  if (role === 'admin' || role === 'platform_owner') {
    return permissionsForRole('admin');
  }
  return resolvePermissions(role, custom ?? catalogPerms ?? null);
}
