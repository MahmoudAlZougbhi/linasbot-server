import type { PublicUser } from '../../api/types';
import { resolvePermissions, type PermissionMap } from '../users/usersPermissions';

export function requestsPermissions(user: PublicUser | null | undefined): PermissionMap {
  if (!user) {
    return resolvePermissions('viewer', null);
  }
  return resolvePermissions(user.role, user.permissions ?? null);
}

export function canViewRequests(user: PublicUser | null | undefined): boolean {
  return requestsPermissions(user).requests === true;
}

export function canManageRequests(user: PublicUser | null | undefined): boolean {
  return requestsPermissions(user).requestsManage === true;
}

export function canNotifyRequests(user: PublicUser | null | undefined): boolean {
  return requestsPermissions(user).requestsNotify === true;
}

export function canManualChatRequests(user: PublicUser | null | undefined): boolean {
  return requestsPermissions(user).requestsManualChat === true;
}

export function canViewSensitiveRequests(user: PublicUser | null | undefined): boolean {
  return requestsPermissions(user).requestsSensitive === true;
}
