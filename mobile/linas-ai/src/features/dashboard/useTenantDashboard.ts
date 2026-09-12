import { useCallback, useEffect, useRef, useState } from 'react';

import { cacheGet, cacheSet, dedupeFetch, isCacheFresh } from '../../cache/queryCache';
import { queryKeys } from '../../cache/queryKeys';
import { QUERY_TTL } from '../../cache/queryTtl';
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

function paintFromCache(
  periodKey: string,
  tz: string,
): { data: TenantDashboard; stale: boolean } | null {
  const key = queryKeys.dashboard(periodKey, tz);
  const hit = cacheGet<TenantDashboard>(key);
  if (!hit) return null;
  return { data: hit.data, stale: !isCacheFresh(key, QUERY_TTL.dashboard) };
}

export function useTenantDashboard(initialPeriod?: DashboardPeriodSelection) {
  const [period, setPeriod] = useState<DashboardPeriodSelection>(
    initialPeriod ?? DEFAULT_DASHBOARD_PERIOD,
  );
  const [tz] = useState(defaultTz);
  const periodKey = dashboardPeriodKey(period);
  const seeded = paintFromCache(periodKey, tz);
  const [state, setState] = useState<DashboardLoadState>(() =>
    seeded
      ? {
          kind: 'ready',
          data: seeded.data,
          periodKey,
          stale: seeded.stale,
          refreshError: null,
          refreshErrorCode: null,
        }
      : { kind: 'loading' },
  );
  const [refreshing, setRefreshing] = useState(false);
  const snapshotRef = useRef<TenantDashboard | null>(seeded?.data ?? null);
  const snapshotPeriodKeyRef = useRef<string | null>(seeded ? periodKey : null);
  const requestIdRef = useRef(0);
  const periodRef = useRef(period);
  periodRef.current = period;

  const load = useCallback(
    async (opts?: { soft?: boolean; force?: boolean }) => {
      const requestId = ++requestIdRef.current;
      const selected = periodRef.current;
      const selectedKey = dashboardPeriodKey(selected);
      const key = queryKeys.dashboard(selectedKey, tz);
      const cached = cacheGet<TenantDashboard>(key);
      if (cached) {
        snapshotRef.current = cached.data;
        snapshotPeriodKeyRef.current = selectedKey;
        setState({
          kind: 'ready',
          data: cached.data,
          periodKey: selectedKey,
          stale: !isCacheFresh(key, QUERY_TTL.dashboard),
          refreshError: null,
          refreshErrorCode: null,
        });
      }
      const hasMatchingSnapshot =
        snapshotRef.current != null && snapshotPeriodKeyRef.current === selectedKey;
      if (!opts?.force && hasMatchingSnapshot && isCacheFresh(key, QUERY_TTL.dashboard)) {
        return;
      }
      const soft = Boolean(opts?.soft || cached) && hasMatchingSnapshot;
      if (soft) setRefreshing(true);
      else if (!hasMatchingSnapshot) setState({ kind: 'loading' });
      try {
        const data = await dedupeFetch(key, () => fetchTenantDashboard(selected, tz));
        if (requestId !== requestIdRef.current) return;
        cacheSet(key, data);
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
    void load({ soft: true });
  }, [load, periodKey]);

  const applyPeriod = useCallback((next: DashboardPeriodSelection) => {
    const nextKey = dashboardPeriodKey(next);
    if (nextKey === dashboardPeriodKey(periodRef.current)) return;
    const painted = paintFromCache(nextKey, tz);
    if (painted) {
      snapshotRef.current = painted.data;
      snapshotPeriodKeyRef.current = nextKey;
      setState({
        kind: 'ready',
        data: painted.data,
        periodKey: nextKey,
        stale: painted.stale,
        refreshError: null,
        refreshErrorCode: null,
      });
    } else {
      snapshotRef.current = null;
      snapshotPeriodKeyRef.current = null;
      setState({ kind: 'loading' });
    }
    setPeriod(next);
  }, [tz]);

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
    refreshIfStale: () => load({ soft: true }),
    state: stateForPeriod,
    refreshing,
    refresh: () => load({ soft: true, force: true }),
    reload: () => load({ soft: false, force: true }),
    tz,
  };
}
