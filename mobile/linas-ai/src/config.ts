import * as Application from 'expo-application';
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

function nativeBinaryLabel(value: string | null, field: string): string {
  const trimmed = (value ?? '').trim();
  if (!trimmed) {
    throw new Error(`Missing ${field} in native binary`);
  }
  return trimmed;
}

// Marketing string stays expo.version / CFBundleShortVersionString (1.0.0) for the
// store update API. EAS remote autoIncrement only bumps iOS CFBundleVersion /
// Android versionCode — that is the number that changes on every TestFlight.
// Read those from expo-application (the IPA/AAB), not expo-constants (stale app.json).
export const APP_VERSION = nativeBinaryLabel(
  Application.nativeApplicationVersion,
  'nativeApplicationVersion',
);
export const APP_BUILD_LABEL = nativeBinaryLabel(
  Application.nativeBuildVersion,
  'nativeBuildVersion',
);
/** Side-menu / Settings — the auto-incrementing native build, e.g. Linas 65. */
export const APP_VERSION_LABEL = `Linas ${APP_BUILD_LABEL}`;

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
