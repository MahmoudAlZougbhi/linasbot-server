import { useCallback, useEffect, useState } from 'react';

import { tokenStore } from '../../auth/tokenStore';
import type { PublicUser } from '../../api/types';
import { classifyRequestsError, fetchRequestsSetupStatus, listRequests } from './requestsApi';
import { canViewRequests } from './requestsPermissions';
import {
  createdAfterForPreset,
  type AssigneeFilter,
  type DatePreset,
  type RequestCard,
  type RequestsErrorKind,
  type TypeFilter,
} from './requestsTypes';

export type RequestsListState = {
  items: RequestCard[];
  counts: Record<string, number>;
  loading: boolean;
  refreshing: boolean;
  loadingMore: boolean;
  error: string | null;
  errorKind: RequestsErrorKind | null;
  setupRequired: boolean;
  hasMore: boolean;
  search: string;
  setSearch: (v: string) => void;
  typeFilter: TypeFilter;
  setTypeFilter: (v: TypeFilter) => void;
  statusFilter: string | null;
  setStatusFilter: (v: string | null) => void;
  channelFilter: string | null;
  setChannelFilter: (v: string | null) => void;
  assigneeFilter: AssigneeFilter;
  setAssigneeFilter: (v: AssigneeFilter) => void;
  datePreset: DatePreset;
  setDatePreset: (v: DatePreset) => void;
  user: PublicUser | null;
  refresh: () => Promise<void>;
  loadMore: () => Promise<void>;
};

export function useRequestsList(enabled: boolean): RequestsListState {
  const [user, setUser] = useState<PublicUser | null>(null);
  const [items, setItems] = useState<RequestCard[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorKind, setErrorKind] = useState<RequestsErrorKind | null>(null);
  const [setupRequired, setSetupRequired] = useState(false);
  const [search, setSearch] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [channelFilter, setChannelFilter] = useState<string | null>(null);
  const [assigneeFilter, setAssigneeFilter] = useState<AssigneeFilter>('all');
  const [datePreset, setDatePreset] = useState<DatePreset>('all');

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(search.trim()), 280);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    void tokenStore.getUser().then(setUser);
  }, [enabled]);

  const load = useCallback(
    async (mode: 'replace' | 'append' | 'quiet') => {
      if (!enabled) {
        setLoading(false);
        return;
      }
      const currentUser = (await tokenStore.getUser()) ?? null;
      setUser(currentUser);
      if (!canViewRequests(currentUser)) {
        setErrorKind('forbidden');
        setError('forbidden');
        setLoading(false);
        setRefreshing(false);
        return;
      }
      if (mode === 'replace') setLoading(true);
      if (mode === 'append') setLoadingMore(true);
      if (mode === 'quiet') setRefreshing(true);
      setError(null);
      setErrorKind(null);
      try {
        const setup = await fetchRequestsSetupStatus();
        setSetupRequired(Boolean(setup.setup_required));
        const page = await listRequests({
          requestType: typeFilter === 'all' ? null : typeFilter,
          status: statusFilter,
          sourceChannel: channelFilter,
          assignedUserId: assigneeFilter === 'me' ? currentUser?.id ?? null : null,
          q: debouncedQ || null,
          cursor: mode === 'append' ? cursor : null,
          createdAfter: createdAfterForPreset(datePreset),
          limit: 25,
        });
        const nextItems = page.items ?? [];
        setCounts(page.counts ?? {});
        setCursor(page.next_cursor ?? null);
        setHasMore(Boolean(page.next_cursor));
        setItems((prev) => (mode === 'append' ? [...prev, ...nextItems] : nextItems));
      } catch (err) {
        const kind = classifyRequestsError(err);
        setErrorKind(kind);
        setError(kind);
      } finally {
        setLoading(false);
        setRefreshing(false);
        setLoadingMore(false);
      }
    },
    [assigneeFilter, channelFilter, cursor, datePreset, debouncedQ, enabled, statusFilter, typeFilter],
  );

  useEffect(() => {
    void load('replace');
    // Reset pagination when filters change — intentionally omit cursor/load identity churn
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, typeFilter, statusFilter, channelFilter, assigneeFilter, datePreset, debouncedQ]);

  return {
    items,
    counts,
    loading,
    refreshing,
    loadingMore,
    error,
    errorKind,
    setupRequired,
    hasMore,
    search,
    setSearch,
    typeFilter,
    setTypeFilter,
    statusFilter,
    setStatusFilter,
    channelFilter,
    setChannelFilter,
    assigneeFilter,
    setAssigneeFilter,
    datePreset,
    setDatePreset,
    user,
    refresh: () => load('quiet'),
    loadMore: async () => {
      if (!hasMore || loadingMore) return;
      await load('append');
    },
  };
}
