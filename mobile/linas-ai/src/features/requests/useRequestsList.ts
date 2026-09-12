import { useCallback, useEffect, useRef, useState } from 'react';

import { tokenStore } from '../../auth/tokenStore';
import type { PublicUser } from '../../api/types';
import { cacheGet, cacheSet, isCacheFresh } from '../../cache/queryCache';
import { queryKeys } from '../../cache/queryKeys';
import { QUERY_TTL } from '../../cache/queryTtl';
import { classifyUsersError, listUsers, type TeamUser } from '../users/usersApi';
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
  hasLoadedOnce: boolean;
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
  refresh: (opts?: { force?: boolean }) => Promise<void>;
  loadMore: () => Promise<void>;
};

type RequestsSnapshot = {
  items: RequestCard[];
  counts: Record<string, number>;
  matched: number;
  hasMore: boolean;
  cursor: string | null;
  setupRequired: boolean;
};

function sourceChannelParam(platforms: string[]): string | null {
  const ids = platforms.filter((id) => id && id !== 'all');
  return ids.length ? ids.join(',') : null;
}

function listCacheKey(filters: RequestFilters, statusBucket: StatusBucket | null, q: string): string {
  return queryKeys.requests(
    [
      statusBucket ?? 'all',
      sourceChannelParam(filters.platforms) || '',
      filters.assignedUserId || '',
      q,
      filters.dateFrom || '',
      filters.dateTo || '',
    ].join('|'),
  );
}

export function useRequestsList(enabled: boolean): RequestsListState {
  const seeded = cacheGet<RequestsSnapshot>(listCacheKey(EMPTY_FILTERS, null, ''));
  const [user, setUser] = useState<PublicUser | null>(null);
  const [items, setItems] = useState<RequestCard[]>(seeded?.data.items ?? []);
  const [counts, setCounts] = useState<Record<string, number>>(seeded?.data.counts ?? {});
  const [matched, setMatched] = useState(seeded?.data.matched ?? 0);
  const [cursor, setCursor] = useState<string | null>(seeded?.data.cursor ?? null);
  const [hasMore, setHasMore] = useState(seeded?.data.hasMore ?? false);
  const [loading, setLoading] = useState(enabled && !seeded);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(Boolean(seeded));
  const hasLoadedOnceRef = useRef(Boolean(seeded));
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorKind, setErrorKind] = useState<RequestsErrorKind | null>(null);
  const [setupRequired, setSetupRequired] = useState(seeded?.data.setupRequired ?? false);
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
      const usersKey = queryKeys.users();
      const hit = cacheGet<TeamUser[]>(usersKey);
      const toStaff = (users: TeamUser[]) =>
        users
          .filter((u) => String(u.status || 'active').toLowerCase() !== 'inactive')
          .map((u) => ({
            id: u.id,
            label: assigneeFirstName(u.name || u.displayName || u.email) || u.email,
          }));
      if (hit) {
        if (!cancelled) setStaff(toStaff(hit.data));
        if (isCacheFresh(usersKey, QUERY_TTL.users)) return;
      }
      try {
        const users = await listUsers();
        cacheSet(usersKey, users);
        if (cancelled) return;
        setStaff(toStaff(users));
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
      const key = listCacheKey(filters, statusBucket, debouncedQ);
      const hit = cacheGet<RequestsSnapshot>(key);
      if (hit && mode !== 'append') {
        setItems(hit.data.items);
        setCounts(hit.data.counts);
        setMatched(hit.data.matched);
        setCursor(hit.data.cursor);
        setHasMore(hit.data.hasMore);
        setSetupRequired(hit.data.setupRequired);
        hasLoadedOnceRef.current = true;
        setHasLoadedOnce(true);
        setLoading(false);
      }
      const currentUser = (await tokenStore.getUser()) ?? null;
      setUser(currentUser);
      if (!canViewRequests(currentUser)) {
        setErrorKind('forbidden');
        setError('forbidden');
        setLoading(false);
        setRefreshing(false);
        if (!hit) setItems([]);
        return;
      }
      if (mode === 'replace' && hit && isCacheFresh(key, QUERY_TTL.requests)) return;
      if (mode === 'replace' && !hasLoadedOnceRef.current) setLoading(true);
      if (mode === 'append') setLoadingMore(true);
      if (mode === 'quiet') setRefreshing(true);
      setError(null);
      setErrorKind(null);
      try {
        const requestArgs = {
          status: statusBucket ? bucketStatuses(statusBucket).join(',') : null,
          sourceChannel: sourceChannelParam(filters.platforms),
          assignedUserId: filters.assignedUserId,
          q: debouncedQ || null,
          cursor: mode === 'append' ? cursor : null,
          createdAfter: filters.dateFrom ? startOfDayIso(filters.dateFrom) : null,
          createdOnOrBefore: filters.dateTo ? endOfDayIso(filters.dateTo) : null,
          limit: 25,
        };
        const [setup, page] =
          mode === 'append'
            ? [null, await listRequests(requestArgs)]
            : await Promise.all([fetchRequestsSetupStatus(), listRequests(requestArgs)]);
        if (setup) setSetupRequired(Boolean(setup.setup_required));
        const nextItems = page.items ?? [];
        const nextCursor = page.next_cursor ?? null;
        const nextCounts = page.counts ?? {};
        const nextMatched = page.matched ?? nextItems.length;
        setCounts(nextCounts);
        setMatched(nextMatched);
        setCursor(nextCursor);
        setHasMore(Boolean(nextCursor));
        setItems((prev) => {
          const rows = mode === 'append' ? [...prev, ...nextItems] : nextItems;
          if (mode !== 'append') {
            cacheSet(key, {
              items: rows,
              counts: nextCounts,
              matched: nextMatched,
              hasMore: Boolean(nextCursor),
              cursor: nextCursor,
              setupRequired: Boolean(setup?.setup_required ?? hit?.data.setupRequired),
            });
          }
          return rows;
        });
      } catch (err) {
        const kind = classifyRequestsError(err);
        setErrorKind(kind);
        setError(kind);
      } finally {
        hasLoadedOnceRef.current = true;
        setHasLoadedOnce(true);
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
    hasLoadedOnce,
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
    refresh: (opts?: { force?: boolean }) => {
      if (!opts?.force) {
        const key = listCacheKey(filters, statusBucket, debouncedQ);
        if (isCacheFresh(key, QUERY_TTL.requests)) return Promise.resolve();
      }
      return load('quiet');
    },
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
