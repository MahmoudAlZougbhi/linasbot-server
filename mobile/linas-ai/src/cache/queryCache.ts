import { QUERY_CACHE_MAX_ENTRIES } from './queryTtl';

type Entry<T> = {
  data: T;
  updatedAt: number;
};

const store = new Map<string, Entry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

function touch(key: string, entry: Entry<unknown>): void {
  store.delete(key);
  store.set(key, entry);
  while (store.size > QUERY_CACHE_MAX_ENTRIES) {
    const oldest = store.keys().next().value;
    if (oldest === undefined) break;
    store.delete(oldest);
  }
}

export function cacheGet<T>(key: string): Entry<T> | null {
  const row = store.get(key);
  if (!row) return null;
  touch(key, row);
  return row as Entry<T>;
}

export function cacheSet<T>(key: string, data: T, now = Date.now()): void {
  touch(key, { data, updatedAt: now });
}

export function cacheInvalidate(prefix: string): void {
  for (const key of [...store.keys()]) {
    if (key === prefix || key.startsWith(prefix)) store.delete(key);
  }
}

export function cacheClear(): void {
  store.clear();
  inflight.clear();
}

export function cacheAgeMs(key: string, now = Date.now()): number | null {
  const row = store.get(key);
  if (!row) return null;
  return now - row.updatedAt;
}

export function isCacheFresh(key: string, ttlMs: number, now = Date.now()): boolean {
  const row = store.get(key);
  if (!row) return false;
  return now - row.updatedAt < ttlMs;
}

export function isCacheStale(key: string, ttlMs: number, now = Date.now()): boolean {
  return !isCacheFresh(key, ttlMs, now);
}

/** One in-flight fetch per key. Parallel callers share the same promise. */
export function dedupeFetch<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key);
  if (existing) return existing as Promise<T>;
  const pending = fetcher().finally(() => {
    if (inflight.get(key) === pending) inflight.delete(key);
  });
  inflight.set(key, pending);
  return pending;
}

export function cacheSize(): number {
  return store.size;
}

/** @internal */
export function __resetQueryCacheForTests(): void {
  store.clear();
  inflight.clear();
}
