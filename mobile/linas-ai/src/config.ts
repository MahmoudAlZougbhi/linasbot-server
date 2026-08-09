import Constants from 'expo-constants';

const extra = (Constants.expoConfig?.extra ?? {}) as { apiBaseUrl?: string };

/** Public API origin only — never embed provider/server secrets. */
export const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE_URL ??
  extra.apiBaseUrl ??
  'https://linasaibot.com';

export const APP_ENV = process.env.EXPO_PUBLIC_APP_ENV ?? 'preview';
export const APP_VERSION = Constants.expoConfig?.version ?? '1.0.0';
export const IOS_BUILD = Constants.expoConfig?.ios?.buildNumber ?? '1';
export const ANDROID_VERSION_CODE = Constants.expoConfig?.android?.versionCode ?? 1;

export const LEGAL_URLS = {
  privacy: `${API_BASE}/privacy-policy`,
  terms: `${API_BASE}/terms`,
  dataDeletion: `${API_BASE}/data-deletion`,
  forgotPassword: `${API_BASE}/forgot-password`,
} as const;
