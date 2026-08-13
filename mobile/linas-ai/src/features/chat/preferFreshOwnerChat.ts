import AsyncStorage from '@react-native-async-storage/async-storage';

/** Survives remount / process kill until the next successful fresh owner bootstrap. */
const KEY = 'linas.ai.preferFreshOwnerChat';

/** Call on logout / auth clear so the next owner session opens empty/new chat. */
export async function markPreferFreshOwnerChat(): Promise<void> {
  await AsyncStorage.setItem(KEY, '1');
}

export async function isPreferFreshOwnerChat(): Promise<boolean> {
  const raw = await AsyncStorage.getItem(KEY);
  return Boolean(raw);
}

/** Clear after a successful fresh bootstrap (new chat created). */
export async function clearPreferFreshOwnerChat(): Promise<void> {
  await AsyncStorage.removeItem(KEY);
}
