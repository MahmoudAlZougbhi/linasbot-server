import { useCallback, useEffect, useRef, useState } from 'react';

import {
  classifyDashboardError,
  dashboardErrorMessage,
  fetchTenantDashboard,
} from './dashboardApi';
import type { DashboardPeriodSelection } from './dashboardFormat';
import { monthStartIso, todayIso } from './dashboardFormat';
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

function defaultPeriod(): DashboardPeriodSelection {
  return { kind: 'custom', start: monthStartIso(), end: todayIso() };
}

export function useTenantDashboard(initialPeriod?: DashboardPeriodSelection) {
  const [period, setPeriod] = useState<DashboardPeriodSelection>(initialPeriod ?? defaultPeriod());
  const [state, setState] = useState<DashboardLoadState>({ kind: 'loading' });
  const [refreshing, setRefreshing] = useState(false);
  const snapshotRef = useRef<TenantDashboard | null>(null);
  const tz = defaultTz();

  const load = useCallback(
    async (opts?: { soft?: boolean }) => {
      const soft = Boolean(opts?.soft);
      if (soft) setRefreshing(true);
      else if (!snapshotRef.current) setState({ kind: 'loading' });
      try {
        const data = await fetchTenantDashboard(period, tz);
        snapshotRef.current = data;
        setState({
          kind: 'ready',
          data,
          stale: false,
          refreshError: null,
          refreshErrorCode: null,
        });
      } catch (err) {
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
        setRefreshing(false);
      }
    },
    [period, tz],
  );

  useEffect(() => {
    void load();
  }, [load]);

  return {
    period,
    setPeriod,
    state,
    refreshing,
    refresh: () => load({ soft: true }),
    reload: () => load({ soft: false }),
    tz,
  };
}
