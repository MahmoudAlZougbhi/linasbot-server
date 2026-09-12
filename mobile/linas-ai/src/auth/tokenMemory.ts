import type { PublicUser } from '../api/types';

/**
 * Process-memory token/user snapshot. SecureStore remains persistence.
 * After boot hydrate, API calls must not wait on the keychain.
 */
let access: string | null = null;
let refresh: string | null = null;
let user: PublicUser | null = null;
let accessHydrated = false;
let refreshHydrated = false;
let userHydrated = false;

export function peekAccessToken(): string | null {
  return accessHydrated ? access : null;
}

export function peekRefreshToken(): string | null {
  return refreshHydrated ? refresh : null;
}

export function peekCachedUser(): PublicUser | null {
  return userHydrated ? user : null;
}

export function isAccessHydrated(): boolean {
  return accessHydrated;
}

export function isRefreshHydrated(): boolean {
  return refreshHydrated;
}

export function isUserHydrated(): boolean {
  return userHydrated;
}

export function rememberAccessToken(value: string | null): void {
  access = value;
  accessHydrated = true;
}

export function rememberRefreshToken(value: string | null): void {
  refresh = value;
  refreshHydrated = true;
}

export function rememberUser(value: PublicUser | null): void {
  user = value;
  userHydrated = true;
}

export function wipeTokenMemory(): void {
  access = null;
  refresh = null;
  user = null;
  accessHydrated = true;
  refreshHydrated = true;
  userHydrated = true;
}

/** @internal tests only — simulates a cold process. */
export function __resetTokenMemoryForTests(): void {
  access = null;
  refresh = null;
  user = null;
  accessHydrated = false;
  refreshHydrated = false;
  userHydrated = false;
}
