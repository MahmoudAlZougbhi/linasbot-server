import { useCallback, useState } from 'react';

/**
 * Gates screen content until the first fetch completes.
 * - `showInitialLoader`: full-screen LinasLoadingIndicator only (no partial UI).
 * - `isRefreshing`: subsequent loads while content stays visible (pull-to-refresh, header refresh).
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
