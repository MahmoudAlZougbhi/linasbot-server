import { useCallback, useEffect, useRef, useState } from 'react';

import {
  classifyDashboardError,
  dashboardErrorMessage,
  fetchTenantDashboard,
} from './dashboardApi';
import {
  DEFAULT_DASHBOARD_PERIOD,
  dashboardPeriodKey,
  isAllTimePeriod,
  type DashboardPeriodSelection,
} from './dashboardFormat';
import type { TenantDashboard } from './dashboardTypes';

export type DashboardLoadState =
  | { kind: 'loading' }
  | {
      kind: 'ready';
      data: TenantDashboard;
      periodKey: string;
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
  const snapshotPeriodKeyRef = useRef<string | null>(null);
  const requestIdRef = useRef(0);
  const periodRef = useRef(period);
  periodRef.current = period;
  const periodKey = dashboardPeriodKey(period);
  const [tz] = useState(defaultTz);

  const load = useCallback(
    async (opts?: { soft?: boolean }) => {
      const requestId = ++requestIdRef.current;
      const selected = periodRef.current;
      const selectedKey = dashboardPeriodKey(selected);
      const hasMatchingSnapshot =
        snapshotRef.current != null && snapshotPeriodKeyRef.current === selectedKey;
      const soft = Boolean(opts?.soft) && hasMatchingSnapshot;
      if (soft) {
        setRefreshing(true);
      } else {
        if (!hasMatchingSnapshot) {
          snapshotRef.current = null;
          snapshotPeriodKeyRef.current = null;
        }
        setState({ kind: 'loading' });
      }
      try {
        const data = await fetchTenantDashboard(selected, tz);
        if (requestId !== requestIdRef.current) return;
        snapshotRef.current = data;
        snapshotPeriodKeyRef.current = selectedKey;
        setState({
          kind: 'ready',
          data,
          periodKey: selectedKey,
          stale: false,
          refreshError: null,
          refreshErrorCode: null,
        });
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        const code = classifyDashboardError(err);
        const message = dashboardErrorMessage(err);
        if (code === 'forbidden' && !hasMatchingSnapshot) {
          setState({ kind: 'forbidden', message });
          return;
        }
        if (hasMatchingSnapshot && snapshotRef.current) {
          setState({
            kind: 'ready',
            data: snapshotRef.current,
            periodKey: selectedKey,
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
  }, [load, periodKey]);

  const applyPeriod = useCallback((next: DashboardPeriodSelection) => {
    const nextKey = dashboardPeriodKey(next);
    if (nextKey !== dashboardPeriodKey(periodRef.current)) {
      snapshotRef.current = null;
      snapshotPeriodKeyRef.current = null;
      setState({ kind: 'loading' });
    }
    setPeriod(next);
  }, []);

  const resetToDefaultPeriod = useCallback(() => {
    if (isAllTimePeriod(periodRef.current)) return;
    applyPeriod(DEFAULT_DASHBOARD_PERIOD);
  }, [applyPeriod]);

  const stateForPeriod =
    state.kind === 'ready' && state.periodKey !== periodKey ? { kind: 'loading' as const } : state;

  return {
    period,
    setPeriod: applyPeriod,
    resetToDefaultPeriod,
    state: stateForPeriod,
    refreshing,
    refresh: () => load({ soft: true }),
    reload: () => load({ soft: false }),
    tz,
  };
}
