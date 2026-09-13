import { useCallback, useEffect, useRef, useState } from 'react';

import { isTransientServiceError } from '../../api/transientError';
import { fetchSubscriptionAccess, type SubscriptionAccess } from './subscriptionAccess';

const UNAVAILABLE_RETRY_MS = 30_000;

/** Authenticated subscription gate state (guest path never gated). */
export function useSubscriptionGate(isAuthenticated: boolean) {
  const [loading, setLoading] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [access, setAccess] = useState<SubscriptionAccess | null>(null);
  const requestGen = useRef(0);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      requestGen.current += 1;
      setAccess(null);
      setUnavailable(false);
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
      setUnavailable(false);
      setAccess(next);
    } catch (err) {
      if (gen !== requestGen.current) {
        return;
      }
      if (isTransientServiceError(err)) {
        setUnavailable(true);
        return;
      }
      setUnavailable(false);
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

  useEffect(() => {
    if (!isAuthenticated || !unavailable) return;
    const timer = setInterval(() => {
      void refresh();
    }, UNAVAILABLE_RETRY_MS);
    return () => clearInterval(timer);
  }, [isAuthenticated, unavailable, refresh]);

  const blocked =
    isAuthenticated && !loading && !unavailable && access !== null && !access.allowed;
  return { loading, access, blocked, unavailable, refresh };
}
