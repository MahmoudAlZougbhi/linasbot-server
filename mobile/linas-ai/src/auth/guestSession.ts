import * as SecureStore from 'expo-secure-store';

import { SECURE_STORE_OPTIONS } from './secureStoreOptions';

const GUEST_ID_KEY = 'linas_guest_session_id';

/** One rotate per JS process so Fast Refresh does not wipe an in-progress guest chat. */
let appLaunchRotated = false;

function randomId(): string {
  const bytes = new Uint8Array(16);
  const cryptoApi = globalThis.crypto;
  if (!cryptoApi || typeof cryptoApi.getRandomValues !== 'function') {
    throw new Error('Secure random generator unavailable');
  }
  cryptoApi.getRandomValues(bytes);
  return `g_${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`;
}

/** Idempotent guest session id persisted in SecureStore for this app session. */
export async function getOrCreateGuestSessionId(): Promise<string> {
  const existing = await SecureStore.getItemAsync(GUEST_ID_KEY, SECURE_STORE_OPTIONS);
  if (existing && existing.length >= 8) {
    return existing;
  }
  const id = randomId();
  await SecureStore.setItemAsync(GUEST_ID_KEY, id, SECURE_STORE_OPTIONS);
  return id;
}

export async function clearGuestSessionId(): Promise<void> {
  await SecureStore.deleteItemAsync(GUEST_ID_KEY, SECURE_STORE_OPTIONS);
}

/** Mint a new guest id so the next guest bootstrap cannot reopen a prior thread. */
export async function rotateGuestSessionId(): Promise<string> {
  await clearGuestSessionId();
  return getOrCreateGuestSessionId();
}

/** Cold start: drop any prior guest thread. Safe to call more than once per process. */
export async function rotateGuestSessionOnAppLaunch(): Promise<void> {
  if (appLaunchRotated) return;
  appLaunchRotated = true;
  await rotateGuestSessionId();
}
