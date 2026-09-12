import AsyncStorage from '@react-native-async-storage/async-storage';

import { cacheRestore } from './queryCache';
import {
  isPersistableQueryKey,
  mergePersistSnapshots,
  QUERY_PERSIST_PREFIX,
  type PersistSnap,
} from './queryPersistLogic';
import { sessionScopeId } from './sessionScope';

export { isPersistableQueryKey, mergePersistSnapshots } from './queryPersistLogic';

const pending = new Map<string, PersistSnap>();
let flushTimer: ReturnType<typeof setTimeout> | null = null;

export function scheduleQueryPersist(key: string, data: unknown, updatedAt: number): void {
  if (!isPersistableQueryKey(key)) return;
  pending.set(key, { data, updatedAt });
  if (flushTimer) return;
  flushTimer = setTimeout(() => {
    flushTimer = null;
    void flushQueryPersist();
  }, 280);
}

export async function hydrateQueryPersist(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(storageKey());
    if (!raw) return;
    const parsed = JSON.parse(raw) as Record<string, PersistSnap>;
    if (!parsed || typeof parsed !== 'object') return;
    for (const [key, row] of Object.entries(parsed)) {
      if (!isPersistableQueryKey(key)) continue;
      if (!row || typeof row.updatedAt !== 'number') continue;
      cacheRestore(key, row.data, row.updatedAt);
    }
  } catch {
    /* empty snapshot is fine */
  }
}

export async function clearQueryPersist(): Promise<void> {
  pending.clear();
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  try {
    const keys = await AsyncStorage.getAllKeys();
    const ours = keys.filter((k) => k.startsWith(QUERY_PERSIST_PREFIX));
    if (ours.length) await AsyncStorage.multiRemove(ours);
  } catch {
    /* ignore */
  }
}

async function flushQueryPersist(): Promise<void> {
  if (!pending.size) return;
  const batch: Record<string, PersistSnap> = {};
  for (const [key, row] of pending) batch[key] = row;
  pending.clear();
  let existing: Record<string, PersistSnap> = {};
  try {
    const raw = await AsyncStorage.getItem(storageKey());
    if (raw) {
      const parsed = JSON.parse(raw) as Record<string, PersistSnap>;
      if (parsed && typeof parsed === 'object') existing = parsed;
    }
  } catch {
    /* rewrite from this batch */
  }
  const snapshot = mergePersistSnapshots(existing, batch);
  try {
    await AsyncStorage.setItem(storageKey(), JSON.stringify(snapshot));
  } catch {
    /* quota — keep RAM cache */
  }
}

function storageKey(): string {
  return `${QUERY_PERSIST_PREFIX}${sessionScopeId()}`;
}
