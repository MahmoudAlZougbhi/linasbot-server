/** Logout / tenant-switch hooks. Feature caches register here — tokenStore.clear() is the trigger. */

type ResetFn = () => void;

const resetters = new Set<ResetFn>();

export function onSessionReset(fn: ResetFn): () => void {
  resetters.add(fn);
  return () => {
    resetters.delete(fn);
  };
}

export function resetSessionCaches(): void {
  for (const fn of resetters) {
    try {
      fn();
    } catch {
      /* one cache must not block the rest */
    }
  }
}
