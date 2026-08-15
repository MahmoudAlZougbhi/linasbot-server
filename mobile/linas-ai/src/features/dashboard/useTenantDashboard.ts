import { useCallback, useEffect, useRef, useState } from 'react';

import {
  classifyDashboardError,
  dashboardErrorMessage,
  fetchTenantDashboard,
} from './dashboardApi';
import {
  DEFAULT_DASHBOARD_PERIOD,
  isAllTimePeriod,
  type DashboardPeriodSelection,
} from './dashboardFormat';
import type { TenantDashboard } from './dashboardTypes';

export type DashboardLoadState =
  | { kind: 'loading' }
  | {
      kind: 'ready';
      data: TenantDashboard;
      stale: boolean;
      refreshError: string | null;
      refreshErrorCode: 'auth' | 'forbidden' | 'offline' | 'other' | null;
    }
  | { kind: 'error'; message: string; code: 'auth' | 'forbidden' | 'offline' | 'other' }
  | { kind: 'forbidden'; message: string };

function defaultTz(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function useTenantDashboard(initialPeriod?: DashboardPeriodSelection) {
  const [period, setPeriod] = useState<DashboardPeriodSelection>(
    initialPeriod ?? DEFAULT_DASHBOARD_PERIOD,
  );
  const [state, setState] = useState<DashboardLoadState>({ kind: 'loading' });
  const [refreshing, setRefreshing] = useState(false);
  const snapshotRef = useRef<TenantDashboard | null>(null);
  const requestIdRef = useRef(0);
  const periodRef = useRef(period);
  periodRef.current = period;
  const [tz] = useState(defaultTz);

  const load = useCallback(
    async (opts?: { soft?: boolean }) => {
      const requestId = ++requestIdRef.current;
      const soft = Boolean(opts?.soft);
      const selected = periodRef.current;
      if (soft) setRefreshing(true);
      else if (!snapshotRef.current) setState({ kind: 'loading' });
      try {
        const data = await fetchTenantDashboard(selected, tz);
        if (requestId !== requestIdRef.current) return;
        snapshotRef.current = data;
        setState({
          kind: 'ready',
          data,
          stale: false,
          refreshError: null,
          refreshErrorCode: null,
        });
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        const code = classifyDashboardError(err);
        const message = dashboardErrorMessage(err);
        if (code === 'forbidden' && !snapshotRef.current) {
          setState({ kind: 'forbidden', message });
          return;
        }
        if (snapshotRef.current) {
          setState({
            kind: 'ready',
            data: snapshotRef.current,
            stale: true,
            refreshError: message,
            refreshErrorCode: code,
          });
          return;
        }
        setState({ kind: 'error', message, code });
      } finally {
        if (requestId === requestIdRef.current) setRefreshing(false);
      }
    },
    [tz],
  );

  useEffect(() => {
    void load();
  }, [load, period]);

  const resetToDefaultPeriod = useCallback(() => {
    setPeriod((prev) => (isAllTimePeriod(prev) ? prev : DEFAULT_DASHBOARD_PERIOD));
  }, []);

  return {
    period,
    setPeriod,
    resetToDefaultPeriod,
    state,
    refreshing,
    refresh: () => load({ soft: true }),
    reload: () => load({ soft: false }),
    tz,
  };
}
