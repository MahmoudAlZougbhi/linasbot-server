import { API_BASE } from '../config';
import { tokenStore } from '../auth/tokenStore';
import { MobileLoginResponseSchema } from './types';

type AuthClearedListener = () => void;

const authClearedListeners = new Set<AuthClearedListener>();
let refreshInFlight: Promise<string | null> | null = null;

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return {};
  return JSON.parse(text) as unknown;
}

/** Subscribe to access+refresh wipe (failed refresh). Used so UI drops authed state. */
export function onAuthCleared(listener: AuthClearedListener): () => void {
  authClearedListeners.add(listener);
  return () => {
    authClearedListeners.delete(listener);
  };
}

function notifyAuthCleared(): void {
  for (const listener of authClearedListeners) {
    try {
      listener();
    } catch {
      /* ignore listener errors */
    }
  }
}

/**
 * Rotate-on-use refresh — single-flight so parallel 401s cannot consume the same
 * refresh token twice and wipe the session.
 */
export async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const refresh = await tokenStore.getRefreshToken();
    if (!refresh) {
      return null;
    }
    try {
      const response = await fetch(`${API_BASE}/api/auth/mobile/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      const body = await parseJson(response);
      if (!response.ok) {
        await tokenStore.clear();
        notifyAuthCleared();
        return null;
      }
      const parsed = MobileLoginResponseSchema.parse(body);
      await tokenStore.setTokens(parsed.access_token, parsed.refresh_token);
      return parsed.access_token;
    } catch {
      return null;
    }
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

/** Return a usable access token, refreshing only when missing. */
export async function ensureAccessToken(): Promise<string | null> {
  let access = await tokenStore.getAccessToken();
  if (!access) {
    access = await refreshAccessToken();
  }
  return access;
}

/** @internal — test helper to reset single-flight state between cases. */
export function __resetAccessTokenStateForTests(): void {
  refreshInFlight = null;
  authClearedListeners.clear();
}
