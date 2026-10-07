import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';

import { SECURE_STORE_OPTIONS } from './secureStoreOptions';

const GUEST_ID_KEY = 'linas_guest_session_id';

/** One rotate per JS process so Fast Refresh does not wipe an in-progress guest chat. */
let appLaunchRotated = false;
/** Set immediately on logout so the guest screen does not wait on the keychain. */
let memoryGuestId: string | null = null;

function randomId(): string {
  const bytes = new Uint8Array(16);
  try {
    Crypto.getRandomValues(bytes);
  } catch {
    const cryptoApi = globalThis.crypto;
    if (cryptoApi && typeof cryptoApi.getRandomValues === 'function') {
      cryptoApi.getRandomValues(bytes);
    } else {
      for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    }
  }
  return `g_${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`;
}

async function readStoredGuestId(): Promise<string | null> {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      const existing = await SecureStore.getItemAsync(GUEST_ID_KEY, SECURE_STORE_OPTIONS);
      if (existing && existing.length >= 8 && existing.length <= 80) return existing;
      return null;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 120));
    }
  }
  return null;
}

/** New guest id in memory only. The screen can switch before SecureStore answers. */
export function rotateGuestSessionIdSync(): string {
  memoryGuestId = randomId();
  return memoryGuestId;
}

/** Idempotent guest session id persisted in SecureStore for this app session. */
export async function getOrCreateGuestSessionId(): Promise<string> {
  if (memoryGuestId && memoryGuestId.length >= 8 && memoryGuestId.length <= 80) {
    return memoryGuestId;
  }
  const existing = await readStoredGuestId();
  if (existing) {
    memoryGuestId = existing;
    return existing;
  }
  const id = randomId();
  memoryGuestId = id;
  try {
    await SecureStore.setItemAsync(GUEST_ID_KEY, id, SECURE_STORE_OPTIONS);
  } catch {
    /* Keychain not ready. The in-memory id still opens this chat. */
  }
  return id;
}

export async function clearGuestSessionId(): Promise<void> {
  await SecureStore.deleteItemAsync(GUEST_ID_KEY, SECURE_STORE_OPTIONS);
}

/** Mint a new guest id so the next guest bootstrap cannot reopen a prior thread. */
export async function rotateGuestSessionId(): Promise<string> {
  const id = memoryGuestId && memoryGuestId.length >= 8 ? memoryGuestId : rotateGuestSessionIdSync();
  memoryGuestId = id;
  try {
    await SecureStore.deleteItemAsync(GUEST_ID_KEY, SECURE_STORE_OPTIONS);
    await SecureStore.setItemAsync(GUEST_ID_KEY, id, SECURE_STORE_OPTIONS);
  } catch {
    /* Memory id is already the session the UI is using. */
  }
  return id;
}

/** Cold start: drop any prior guest thread. Safe to call more than once per process. */
export async function rotateGuestSessionOnAppLaunch(): Promise<void> {
  if (appLaunchRotated) return;
  appLaunchRotated = true;
  await rotateGuestSessionId();
}
