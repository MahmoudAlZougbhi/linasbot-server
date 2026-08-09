import * as SecureStore from 'expo-secure-store';

const GUEST_ID_KEY = 'linas_guest_session_id';

function randomId(): string {
  const bytes = new Uint8Array(16);
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Math.floor(Math.random() * 256);
  }
  return `g_${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`;
}

/** Idempotent guest session id persisted in SecureStore. */
export async function getOrCreateGuestSessionId(): Promise<string> {
  const existing = await SecureStore.getItemAsync(GUEST_ID_KEY);
  if (existing && existing.length >= 8) {
    return existing;
  }
  const id = randomId();
  await SecureStore.setItemAsync(GUEST_ID_KEY, id);
  return id;
}

export async function clearGuestSessionId(): Promise<void> {
  await SecureStore.deleteItemAsync(GUEST_ID_KEY);
}
