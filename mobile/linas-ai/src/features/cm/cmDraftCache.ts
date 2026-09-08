/** In-memory CM draft snapshot so section remounts paint instantly, then refresh. */

export type CachedCmDraft = {
  etag: string | null;
  payload: Record<string, unknown>;
};

const cache = new Map<string, CachedCmDraft>();

export function peekCmDraftCache(section: string): CachedCmDraft | null {
  return cache.get(section) ?? null;
}

export function writeCmDraftCache(section: string, row: CachedCmDraft): void {
  cache.set(section, row);
}
