import { useCallback, useEffect, useRef, useState } from 'react';

import { checkAppVersion, type AppVersionCheck } from './appVersionApi';

/** Public version check on cold start — fails open so offline installs keep working. */
export function useAppVersionCheck(enabled: boolean) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AppVersionCheck | null>(null);
  const requestGen = useRef(0);

  const refresh = useCallback(async () => {
    if (!enabled) {
      requestGen.current += 1;
      setResult(null);
      setLoading(false);
      return;
    }
    const gen = ++requestGen.current;
    setLoading(true);
    try {
      const next = await checkAppVersion();
      if (gen !== requestGen.current) return;
      setResult(next);
    } catch {
      if (gen !== requestGen.current) return;
      setResult(null);
    } finally {
      if (gen === requestGen.current) {
        setLoading(false);
      }
    }
  }, [enabled]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const forceUpdate = !loading && result?.state === 'force_update';
  const updateAvailable = !loading && result?.state === 'update_available';

  return { loading, result, forceUpdate, updateAvailable, refresh };
}
