import { Platform } from 'react-native';
import Constants from 'expo-constants';

type Extra = {
  apiBaseUrl?: string;
  googleWebClientId?: string;
  googleIosClientId?: string;
  googleAndroidClientId?: string;
};

const extra = (Constants.expoConfig?.extra ?? {}) as Extra;

/** Reverse iOS URL scheme already in app.json (`com.googleusercontent.apps.<id>`). */
function iosClientIdFromExpoScheme(): string {
  const scheme = Constants.expoConfig?.scheme;
  const schemes = Array.isArray(scheme) ? scheme : scheme ? [scheme] : [];
  const prefix = 'com.googleusercontent.apps.';
  for (const raw of schemes) {
    const value = String(raw);
    if (!value.startsWith(prefix)) continue;
    const id = value.slice(prefix.length).trim();
    if (id) return `${id}.apps.googleusercontent.com`;
  }
  return '';
}

/** Existing Google OAuth clients (docs/release/GOOGLE_SIGN_IN_WIRING.md). Public client IDs only. */
export const GOOGLE_WEB_CLIENT_ID = (
  process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID ||
  extra.googleWebClientId ||
  ''
).trim();
export const GOOGLE_IOS_CLIENT_ID = (
  process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID ||
  extra.googleIosClientId ||
  iosClientIdFromExpoScheme()
).trim();
export const GOOGLE_ANDROID_CLIENT_ID = (
  process.env.EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID ||
  extra.googleAndroidClientId ||
  ''
).trim();

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
export const SUPPORT_EMAIL = 'support@linasai.com';

export const LEGAL_URLS = {
  privacy: `${LEGAL_PUBLIC_BASE}/privacy-policy`,
  terms: `${LEGAL_PUBLIC_BASE}/terms`,
  dataDeletion: `${LEGAL_PUBLIC_BASE}/data-deletion`,
  contact: `${LEGAL_PUBLIC_BASE}/contact`,
  forgotPassword: `${API_BASE}/forgot-password`,
  supportMailto: `mailto:${SUPPORT_EMAIL}`,
} as const;
