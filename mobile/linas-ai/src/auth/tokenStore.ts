import * as SecureStore from 'expo-secure-store';

import { PublicUserSchema, type PublicUser } from '../api/types';
import { SECURE_STORE_OPTIONS } from './secureStoreOptions';

const ACCESS_KEY = 'linas_access_token';
const REFRESH_KEY = 'linas_refresh_token';
const USER_KEY = 'linas_user_json';

export const tokenStore = {
  async getAccessToken(): Promise<string | null> {
    return SecureStore.getItemAsync(ACCESS_KEY, SECURE_STORE_OPTIONS);
  },
  async getRefreshToken(): Promise<string | null> {
    return SecureStore.getItemAsync(REFRESH_KEY, SECURE_STORE_OPTIONS);
  },
  async setTokens(access: string, refresh: string): Promise<void> {
    await SecureStore.setItemAsync(ACCESS_KEY, access, SECURE_STORE_OPTIONS);
    await SecureStore.setItemAsync(REFRESH_KEY, refresh, SECURE_STORE_OPTIONS);
  },
  async setUser(user: PublicUser): Promise<void> {
    await SecureStore.setItemAsync(USER_KEY, JSON.stringify(user), SECURE_STORE_OPTIONS);
  },
  async getUser(): Promise<PublicUser | null> {
    let raw: string | null;
    try {
      raw = await SecureStore.getItemAsync(USER_KEY, SECURE_STORE_OPTIONS);
    } catch {
      return null;
    }
    if (!raw) {
      return null;
    }
    try {
      const parsed = JSON.parse(raw) as unknown;
      const result = PublicUserSchema.safeParse(parsed);
      if (!result.success) {
        await SecureStore.deleteItemAsync(USER_KEY, SECURE_STORE_OPTIONS);
        return null;
      }
      return result.data;
    } catch {
      await SecureStore.deleteItemAsync(USER_KEY, SECURE_STORE_OPTIONS);
      return null;
    }
  },
  async clear(): Promise<void> {
    await SecureStore.deleteItemAsync(ACCESS_KEY, SECURE_STORE_OPTIONS);
    await SecureStore.deleteItemAsync(REFRESH_KEY, SECURE_STORE_OPTIONS);
    await SecureStore.deleteItemAsync(USER_KEY, SECURE_STORE_OPTIONS);
  },
};
