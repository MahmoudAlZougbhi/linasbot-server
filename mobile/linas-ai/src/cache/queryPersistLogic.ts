export const QUERY_PERSIST_MAX = 12;
export const QUERY_PERSIST_PREFIX = 'linas.q.v1:';

/** Tenant-scoped snapshots only — no tokens, no thread bodies. */
export const QUERY_PERSIST_NEEDLES = [
  '|dashboard|',
  '|products',
  '|livechat|inbox|',
  '|cm|hub',
  '|integrations',
  '|billing',
] as const;

export type PersistSnap = { data: unknown; updatedAt: number };

export function isPersistableQueryKey(key: string): boolean {
  return QUERY_PERSIST_NEEDLES.some((needle) => key.includes(needle));
}

export function mergePersistSnapshots(
  existing: Record<string, PersistSnap>,
  batch: Record<string, PersistSnap>,
  max = QUERY_PERSIST_MAX,
): Record<string, PersistSnap> {
  const snapshot: Record<string, PersistSnap> = { ...existing };
  Object.assign(snapshot, batch);
  for (const key of Object.keys(snapshot)) {
    if (!isPersistableQueryKey(key)) delete snapshot[key];
  }
  const keys = Object.keys(snapshot);
  if (keys.length > max) {
    keys
      .sort((a, b) => snapshot[a].updatedAt - snapshot[b].updatedAt)
      .slice(0, keys.length - max)
      .forEach((k) => {
        delete snapshot[k];
      });
  }
  return snapshot;
}
