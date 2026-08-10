import { useCallback, useEffect, useRef, useState } from 'react';

import { fetchSubscriptionAccess, type SubscriptionAccess } from './subscriptionAccess';

/** Authenticated subscription gate state (guest path never gated). */
export function useSubscriptionGate(isAuthenticated: boolean) {
  const [loading, setLoading] = useState(false);
  const [access, setAccess] = useState<SubscriptionAccess | null>(null);
  const requestGen = useRef(0);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      requestGen.current += 1;
      setAccess(null);
      setLoading(false);
      return;
    }
    const gen = ++requestGen.current;
    setLoading(true);
    try {
      const next = await fetchSubscriptionAccess();
      // Ignore stale responses — login triggers effect refresh + explicit refresh;
      // a late fail-closed must not overwrite a newer success (Linas Laser reopen bug).
      if (gen !== requestGen.current) {
        return;
      }
      setAccess(next);
    } catch {
      if (gen !== requestGen.current) {
        return;
      }
      // Fail closed for authenticated owners — no silent unlock.
      setAccess({
        allowed: false,
        planId: null,
        status: null,
        iapPurchaseInApp: false,
        note: null,
      });
    } finally {
      if (gen === requestGen.current) {
        setLoading(false);
      }
    }
  }, [isAuthenticated]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const blocked = isAuthenticated && !loading && access !== null && !access.allowed;
  return { loading, access, blocked, refresh };
}
