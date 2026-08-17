import { useCallback, useEffect, useRef, useState } from 'react';

import { classifyLiveChatError, fetchUnifiedChats, setOperatorAvailable } from './liveChatApi';
import { appendInboxPage, mergeInboxPollPage } from './inboxListMerge';
import {
  type InboxFilter,
  type ChannelFilter,
  type LiveChatItem,
} from './liveChatTypes';

const POLL_MS = 20_000;
const PAGE_SIZE = 30;

export function useLiveChatInbox() {
  const [chats, setChats] = useState<LiveChatItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorKind, setErrorKind] = useState<'forbidden' | 'auth' | 'other' | null>(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<InboxFilter>('all');
  const [channel, setChannel] = useState<ChannelFilter>('all');
  const [hasMore, setHasMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [indexRebuild, setIndexRebuild] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const requestIdRef = useRef(0);
  const nextCursorRef = useRef<string | null>(null);
  const hasMoreRef = useRef(false);
  const paginatedBeyondFirstRef = useRef(false);
  const loadingMoreRef = useRef(false);

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [search]);

  const load = useCallback(
    async (mode: 'initial' | 'refresh' | 'poll' = 'initial') => {
      const requestId = ++requestIdRef.current;
      if (mode === 'initial') setLoading(true);
      if (mode === 'refresh') setRefreshing(true);
      try {
        const data = await fetchUnifiedChats({
          search: debouncedSearch,
          page: 1,
          pageSize: PAGE_SIZE,
          filter,
          channel,
        });
        if (requestId !== requestIdRef.current) return;
        const rows = data.chats ?? [];
        const rebuild = Boolean(data.requires_index_rebuild || data.index_empty);
        // Show whatever rows exist. success:false with no chats is a load error, not empty —
        // unless the server signaled an empty index / rebuild (not a hard outage).
        if (rows.length === 0 && data.success === false && !rebuild) {
          throw new Error(data.error || 'Could not load conversations.');
        }
        if (mode === 'poll' && paginatedBeyondFirstRef.current) {
          setChats((prev) => mergeInboxPollPage(prev, rows));
        } else {
          paginatedBeyondFirstRef.current = false;
          setChats(rows);
          const more = Boolean(data.has_more);
          const cursor = data.next_cursor ?? null;
          hasMoreRef.current = more;
          nextCursorRef.current = cursor;
          setHasMore(more);
          setNextCursor(cursor);
        }
        setTotal(typeof data.total === 'number' ? data.total : rows.length);
        setIndexRebuild(rebuild);
        setError(null);
        setErrorKind(null);
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        if (mode !== 'poll') {
          const kind = classifyLiveChatError(err);
          setErrorKind(kind);
          setError(
            kind === 'forbidden'
              ? 'You do not have permission for Live Chat.'
              : err instanceof Error
                ? err.message
                : 'Could not load conversations.',
          );
          if (mode === 'initial') setChats([]);
        }
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false);
          setHasLoadedOnce(true);
          setRefreshing(false);
        }
      }
    },
    [debouncedSearch, filter, channel],
  );

  const loadMore = useCallback(async () => {
    if (!hasMoreRef.current || loadingMoreRef.current) return;
    const cursor = nextCursorRef.current;
    if (!cursor) {
      hasMoreRef.current = false;
      setHasMore(false);
      return;
    }
    const requestId = requestIdRef.current;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const data = await fetchUnifiedChats({
        search: debouncedSearch,
        page: 1,
        pageSize: PAGE_SIZE,
        cursor,
        filter,
        channel,
      });
      if (requestId !== requestIdRef.current) return;
      setChats((prev) => {
        const merged = appendInboxPage(prev, data.chats ?? []);
        if (merged.length > prev.length) paginatedBeyondFirstRef.current = true;
        return merged;
      });
      const more = Boolean(data.has_more);
      const next = data.next_cursor ?? null;
      hasMoreRef.current = more;
      nextCursorRef.current = next;
      setHasMore(more);
      setNextCursor(next);
    } catch {
      // Keep existing list.
    } finally {
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, [debouncedSearch, filter, channel]);

  useEffect(() => {
    void setOperatorAvailable();
    void load('initial');
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => void load('poll'), POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  return {
    chats,
    loading,
    refreshing,
    loadingMore,
    hasLoadedOnce,
    error,
    errorKind,
    search,
    setSearch,
    filter,
    setFilter,
    channel,
    setChannel,
    hasMore,
    total,
    indexRebuild,
    refresh: () => void load('refresh'),
    loadMore,
    reloadQuiet: () => void load('poll'),
  };
}
