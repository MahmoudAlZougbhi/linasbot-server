import { Platform } from 'react-native';
import Constants from 'expo-constants';

const extra = (Constants.expoConfig?.extra ?? {}) as { apiBaseUrl?: string };

/** Public API origin only — never embed provider/server secrets. */
export const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE_URL ??
  extra.apiBaseUrl ??
  'https://linasaibot.com';

export const APP_ENV = process.env.EXPO_PUBLIC_APP_ENV ?? 'preview';
// Live from expo-constants (values baked into each native build). Never hardcode.
// Marketing version stays expo.version (e.g. 1.0.0). EAS testflight/production use
// cli.appVersionSource=remote + autoIncrement so iOS buildNumber / Android versionCode
// bump on every ship without a manual commit (see eas.json + README Versioning).
export const APP_VERSION = Constants.expoConfig?.version ?? '1.0.0';
export const IOS_BUILD = Constants.expoConfig?.ios?.buildNumber ?? '1';
export const ANDROID_VERSION_CODE = Constants.expoConfig?.android?.versionCode ?? 1;
export const APP_BUILD_LABEL = Platform.OS === 'ios' ? IOS_BUILD : String(ANDROID_VERSION_CODE);
/** Side-menu / About — shows marketing version · platform build so each TF is visible. */
export const APP_VERSION_LABEL = `Linas ${APP_VERSION} · ${APP_BUILD_LABEL}`;

/** Canonical public legal origin (Meta App Review / store listings). */
export const LEGAL_PUBLIC_BASE = 'https://www.linasaibot.com';

/** Public support / legal contact — keep in sync with compliance pages + PUBLIC_SITE. */
export const SUPPORT_EMAIL = 'Mahmoudalzougbhi@gmail.com';

export const LEGAL_URLS = {
  privacy: `${LEGAL_PUBLIC_BASE}/privacy-policy`,
  terms: `${LEGAL_PUBLIC_BASE}/terms`,
  dataDeletion: `${LEGAL_PUBLIC_BASE}/data-deletion`,
  contact: `${LEGAL_PUBLIC_BASE}/contact`,
  forgotPassword: `${API_BASE}/forgot-password`,
  supportMailto: `mailto:${SUPPORT_EMAIL}`,
} as const;
