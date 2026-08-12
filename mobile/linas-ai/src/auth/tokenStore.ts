import * as SecureStore from 'expo-secure-store';

import { PublicUserSchema, type PublicUser } from '../api/types';

const ACCESS_KEY = 'linas_access_token';
const REFRESH_KEY = 'linas_refresh_token';
const USER_KEY = 'linas_user_json';

export const tokenStore = {
  async getAccessToken(): Promise<string | null> {
    return SecureStore.getItemAsync(ACCESS_KEY);
  },
  async getRefreshToken(): Promise<string | null> {
    return SecureStore.getItemAsync(REFRESH_KEY);
  },
  async setTokens(access: string, refresh: string): Promise<void> {
    await SecureStore.setItemAsync(ACCESS_KEY, access);
    await SecureStore.setItemAsync(REFRESH_KEY, refresh);
  },
  async setUser(user: PublicUser): Promise<void> {
    await SecureStore.setItemAsync(USER_KEY, JSON.stringify(user));
  },
  async getUser(): Promise<PublicUser | null> {
    const raw = await SecureStore.getItemAsync(USER_KEY);
    if (!raw) {
      return null;
    }
    try {
      const parsed = JSON.parse(raw) as unknown;
      const result = PublicUserSchema.safeParse(parsed);
      if (!result.success) {
        await SecureStore.deleteItemAsync(USER_KEY);
        return null;
      }
      return result.data;
    } catch {
      await SecureStore.deleteItemAsync(USER_KEY);
      return null;
    }
  },
  async clear(): Promise<void> {
    await SecureStore.deleteItemAsync(ACCESS_KEY);
    await SecureStore.deleteItemAsync(REFRESH_KEY);
    await SecureStore.deleteItemAsync(USER_KEY);
  },
};
