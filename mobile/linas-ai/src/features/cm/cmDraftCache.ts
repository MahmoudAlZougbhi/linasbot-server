/** In-memory CM draft snapshot so section remounts paint instantly, then refresh. */

import { scopedCacheKey } from '../../cache/sessionScope';

export type CachedCmDraft = {
  etag: string | null;
  payload: Record<string, unknown>;
  updatedAt: number;
};

const MAX_ENTRIES = 12;
const cache = new Map<string, CachedCmDraft>();

function draftKey(section: string): string {
  return scopedCacheKey(['cmDraft', section]);
}

export function peekCmDraftCache(section: string): CachedCmDraft | null {
  return cache.get(draftKey(section)) ?? null;
}

export function writeCmDraftCache(section: string, row: Omit<CachedCmDraft, 'updatedAt'>): void {
  const key = draftKey(section);
  cache.delete(key);
  cache.set(key, { ...row, updatedAt: Date.now() });
  while (cache.size > MAX_ENTRIES) {
    const oldest = cache.keys().next().value;
    if (oldest === undefined) break;
    cache.delete(oldest);
  }
}

export function isCmDraftFresh(section: string, ttlMs: number, now = Date.now()): boolean {
  const hit = cache.get(draftKey(section));
  if (!hit) return false;
  return now - hit.updatedAt < ttlMs;
}

export function clearCmDraftCache(): void {
  cache.clear();
}
