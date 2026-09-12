import { useCallback, useState } from 'react';

/**
 * First-fetch vs refresh flags. Chrome always paints; cold body uses ScreenSkeleton.
 * - `showInitialLoader`: cold body has no cache yet (skeleton, never a blank spinner screen).
 * - `isRefreshing`: subsequent loads while cached content stays visible.
 */
export function useScreenLoadGate(initialLoading = true) {
  const [loading, setLoading] = useState(initialLoading);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  const markLoaded = useCallback(() => {
    setLoading(false);
    setHasLoadedOnce(true);
  }, []);

  const showInitialLoader = !hasLoadedOnce;
  const isRefreshing = loading && hasLoadedOnce;

  return {
    loading,
    setLoading,
    hasLoadedOnce,
    setHasLoadedOnce,
    showInitialLoader,
    isRefreshing,
    markLoaded,
  };
}
