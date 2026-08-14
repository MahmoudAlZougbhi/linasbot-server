import { useCallback, useEffect, useState } from 'react';

import { tokenStore } from '../../auth/tokenStore';
import type { PublicUser } from '../../api/types';
import { classifyUsersError, listUsers } from '../users/usersApi';
import { classifyRequestsError, fetchRequestsSetupStatus, listRequests } from './requestsApi';
import { assigneeFirstName, bucketStatuses, endOfDayIso, startOfDayIso } from './requestsFormat';
import { canViewRequests } from './requestsPermissions';
import type { RequestCard, RequestsErrorKind, StatusBucket } from './requestsTypes';

export type StaffPick = { id: string; label: string };

export type RequestFilters = {
  platforms: string[];
  dateFrom: string | null;
  dateTo: string | null;
  assignedUserId: string | null;
};

const EMPTY_FILTERS: RequestFilters = {
  platforms: [],
  dateFrom: null,
  dateTo: null,
  assignedUserId: null,
};

export type RequestsListState = {
  items: RequestCard[];
  counts: Record<string, number>;
  matched: number;
  loading: boolean;
  refreshing: boolean;
  loadingMore: boolean;
  error: string | null;
  errorKind: RequestsErrorKind | null;
  setupRequired: boolean;
  hasMore: boolean;
  search: string;
  setSearch: (v: string) => void;
  statusBucket: StatusBucket | null;
  setStatusBucket: (v: StatusBucket | null) => void;
  filters: RequestFilters;
  applyFilters: (next: RequestFilters) => void;
  staff: StaffPick[];
  user: PublicUser | null;
  patchItem: (item: RequestCard) => void;
  refresh: () => Promise<void>;
  loadMore: () => Promise<void>;
};

function sourceChannelParam(platforms: string[]): string | null {
  const ids = platforms.filter((id) => id && id !== 'all');
  return ids.length ? ids.join(',') : null;
}

export function useRequestsList(enabled: boolean): RequestsListState {
  const [user, setUser] = useState<PublicUser | null>(null);
  const [items, setItems] = useState<RequestCard[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [matched, setMatched] = useState(0);
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
  const [statusBucket, setStatusBucket] = useState<StatusBucket | null>(null);
  const [filters, setFilters] = useState<RequestFilters>(EMPTY_FILTERS);
  const [staff, setStaff] = useState<StaffPick[]>([]);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(search.trim()), 280);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    void tokenStore.getUser().then(setUser);
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    void (async () => {
      try {
        const users = await listUsers();
        if (cancelled) return;
        setStaff(
          users
            .filter((u) => String(u.status || 'active').toLowerCase() !== 'inactive')
            .map((u) => ({
              id: u.id,
              label: assigneeFirstName(u.name || u.displayName || u.email) || u.email,
            })),
        );
      } catch (err) {
        const me = await tokenStore.getUser();
        if (cancelled) return;
        if (me) {
          setStaff([
            { id: me.id, label: assigneeFirstName(me.name || me.displayName || me.email) || me.email },
          ]);
        } else if (classifyUsersError(err) !== 'forbidden') {
          setStaff([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
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
          status: statusBucket ? bucketStatuses(statusBucket).join(',') : null,
          sourceChannel: sourceChannelParam(filters.platforms),
          assignedUserId: filters.assignedUserId,
          q: debouncedQ || null,
          cursor: mode === 'append' ? cursor : null,
          createdAfter: filters.dateFrom ? startOfDayIso(filters.dateFrom) : null,
          createdOnOrBefore: filters.dateTo ? endOfDayIso(filters.dateTo) : null,
          limit: 25,
        });
        const nextItems = page.items ?? [];
        setCounts(page.counts ?? {});
        setMatched(page.matched ?? nextItems.length);
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
    [cursor, debouncedQ, enabled, filters, statusBucket],
  );

  useEffect(() => {
    void load('replace');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, statusBucket, filters, debouncedQ]);

  return {
    items,
    counts,
    matched,
    loading,
    refreshing,
    loadingMore,
    error,
    errorKind,
    setupRequired,
    hasMore,
    search,
    setSearch,
    statusBucket,
    setStatusBucket,
    filters,
    applyFilters: setFilters,
    staff,
    user,
    patchItem: (item) => {
      setItems((prev) => prev.map((row) => (row.request_id === item.request_id ? { ...row, ...item } : row)));
    },
    refresh: () => load('quiet'),
    loadMore: async () => {
      if (!hasMore || loadingMore) return;
      await load('append');
    },
  };
}

export async function previewMatchedCount(filters: RequestFilters, q: string): Promise<number> {
  const page = await listRequests({
    sourceChannel: sourceChannelParam(filters.platforms),
    assignedUserId: filters.assignedUserId,
    q: q.trim() || null,
    createdAfter: filters.dateFrom ? startOfDayIso(filters.dateFrom) : null,
    createdOnOrBefore: filters.dateTo ? endOfDayIso(filters.dateTo) : null,
    limit: 1,
  });
  return page.matched ?? page.items.length;
}
