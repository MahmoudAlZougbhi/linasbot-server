import { useCallback, useEffect, useState } from 'react';

import { fetchSubscriptionAccess, type SubscriptionAccess } from './subscriptionAccess';

/** Authenticated subscription gate state (guest path never gated). */
export function useSubscriptionGate(isAuthenticated: boolean) {
  const [loading, setLoading] = useState(false);
  const [access, setAccess] = useState<SubscriptionAccess | null>(null);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      setAccess(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setAccess(await fetchSubscriptionAccess());
    } catch {
      // Fail closed for authenticated owners — no silent unlock.
      setAccess({
        allowed: false,
        planId: null,
        status: null,
        iapPurchaseInApp: false,
        note: null,
      });
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const blocked = isAuthenticated && !loading && access !== null && !access.allowed;
  return { loading, access, blocked, refresh };
}
