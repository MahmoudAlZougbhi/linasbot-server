import { Platform } from 'react-native';
import Constants from 'expo-constants';

const extra = (Constants.expoConfig?.extra ?? {}) as { apiBaseUrl?: string };

/** Public API origin only — never embed provider/server secrets. */
export const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE_URL ??
  extra.apiBaseUrl ??
  'https://linasaibot.com';

export const APP_ENV = process.env.EXPO_PUBLIC_APP_ENV ?? 'preview';
// Live from expo-constants/app.json — never hardcode. EAS production+testflight autoIncrement bumps buildNumber/versionCode each ship (see eas.json).
export const APP_VERSION = Constants.expoConfig?.version ?? '1.0.0';
export const IOS_BUILD = Constants.expoConfig?.ios?.buildNumber ?? '1';
export const ANDROID_VERSION_CODE = Constants.expoConfig?.android?.versionCode ?? 1;
export const APP_BUILD_LABEL = Platform.OS === 'ios' ? IOS_BUILD : String(ANDROID_VERSION_CODE);
/** Side-menu / About label — single source for NavDrawer + Settings. */
export const APP_VERSION_LABEL = `Linas ${APP_VERSION} · ${APP_BUILD_LABEL}`;

export const LEGAL_URLS = {
  privacy: `${API_BASE}/privacy-policy`,
  terms: `${API_BASE}/terms`,
  dataDeletion: `${API_BASE}/data-deletion`,
  forgotPassword: `${API_BASE}/forgot-password`,
} as const;
