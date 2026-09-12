import * as SecureStore from 'expo-secure-store';

import { PublicUserSchema, type PublicUser } from '../api/types';
import { resetSessionCaches } from '../cache/sessionReset';
import { SECURE_STORE_OPTIONS } from './secureStoreOptions';
import {
  isAccessHydrated,
  isRefreshHydrated,
  isUserHydrated,
  peekAccessToken,
  peekCachedUser,
  peekRefreshToken,
  rememberAccessToken,
  rememberRefreshToken,
  rememberUser,
  wipeTokenMemory,
} from './tokenMemory';

const ACCESS_KEY = 'linas_access_token';
const REFRESH_KEY = 'linas_refresh_token';
const USER_KEY = 'linas_user_json';

export const tokenStore = {
  async getAccessToken(): Promise<string | null> {
    if (isAccessHydrated()) return peekAccessToken();
    const value = await SecureStore.getItemAsync(ACCESS_KEY, SECURE_STORE_OPTIONS);
    rememberAccessToken(value);
    return value;
  },
  async getRefreshToken(): Promise<string | null> {
    if (isRefreshHydrated()) return peekRefreshToken();
    const value = await SecureStore.getItemAsync(REFRESH_KEY, SECURE_STORE_OPTIONS);
    rememberRefreshToken(value);
    return value;
  },
  async setTokens(access: string, refresh: string): Promise<void> {
    rememberAccessToken(access);
    rememberRefreshToken(refresh);
    await SecureStore.setItemAsync(ACCESS_KEY, access, SECURE_STORE_OPTIONS);
    await SecureStore.setItemAsync(REFRESH_KEY, refresh, SECURE_STORE_OPTIONS);
  },
  async setUser(user: PublicUser): Promise<void> {
    const prev = peekCachedUser();
    if (isUserHydrated() && (prev?.id ?? null) !== user.id) {
      resetSessionCaches();
    }
    rememberUser(user);
    await SecureStore.setItemAsync(USER_KEY, JSON.stringify(user), SECURE_STORE_OPTIONS);
  },
  async getUser(): Promise<PublicUser | null> {
    if (isUserHydrated()) return peekCachedUser();
    let raw: string | null;
    try {
      raw = await SecureStore.getItemAsync(USER_KEY, SECURE_STORE_OPTIONS);
    } catch {
      rememberUser(null);
      return null;
    }
    if (!raw) {
      rememberUser(null);
      return null;
    }
    try {
      const parsed = JSON.parse(raw) as unknown;
      const result = PublicUserSchema.safeParse(parsed);
      if (!result.success) {
        await SecureStore.deleteItemAsync(USER_KEY, SECURE_STORE_OPTIONS);
        rememberUser(null);
        return null;
      }
      rememberUser(result.data);
      return result.data;
    } catch {
      await SecureStore.deleteItemAsync(USER_KEY, SECURE_STORE_OPTIONS);
      rememberUser(null);
      return null;
    }
  },
  async clear(): Promise<void> {
    wipeTokenMemory();
    resetSessionCaches();
    await SecureStore.deleteItemAsync(ACCESS_KEY, SECURE_STORE_OPTIONS);
    await SecureStore.deleteItemAsync(REFRESH_KEY, SECURE_STORE_OPTIONS);
    await SecureStore.deleteItemAsync(USER_KEY, SECURE_STORE_OPTIONS);
  },
};
