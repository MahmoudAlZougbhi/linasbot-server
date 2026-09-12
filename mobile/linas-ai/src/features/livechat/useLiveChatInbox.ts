import { useCallback, useEffect, useRef, useState } from 'react';

import { classifyLiveChatError, fetchUnifiedChats, setOperatorAvailable } from './liveChatApi';
import { appendInboxPage, applyInboxNewMessage, mergeInboxPollPage } from './inboxListMerge';
import {
  type InboxFilter,
  type ChannelFilter,
  type LiveChatItem,
  type UnifiedChats,
  normalizeStatus,
} from './liveChatTypes';

function waitingCountFromResponse(data: UnifiedChats, filter: InboxFilter, rows: LiveChatItem[]): number {
  const fromCounters = data.counters?.waiting;
  if (typeof fromCounters === 'number' && fromCounters >= 0) return fromCounters;
  if (filter === 'waiting' && typeof data.total === 'number') return data.total;
  return rows.filter((chat) => normalizeStatus(chat) === 'waiting_human').length;
}

const PAGE_SIZE = 30;

export function useLiveChatInbox(enabled = true) {
  const [chats, setChats] = useState<LiveChatItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const hasLoadedOnceRef = useRef(false);
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
  const [waitingCount, setWaitingCount] = useState(0);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const requestIdRef = useRef(0);
  const nextCursorRef = useRef<string | null>(null);
  const hasMoreRef = useRef(false);
  const paginatedBeyondFirstRef = useRef(false);
  const loadingMoreRef = useRef(false);
  const chatsRef = useRef<LiveChatItem[]>([]);

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
      if (mode === 'initial' && !hasLoadedOnceRef.current) setLoading(true);
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
        setWaitingCount(waitingCountFromResponse(data, filter, rows));
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
          hasLoadedOnceRef.current = true;
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

  chatsRef.current = chats;

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      hasLoadedOnceRef.current = true;
      setHasLoadedOnce(true);
      return;
    }
    void setOperatorAvailable();
    void load('initial');
  }, [load, enabled]);

  const applyNewMessage = useCallback(
    (data: Record<string, unknown>, openConversationId?: string | null) => {
      const result = applyInboxNewMessage(chatsRef.current, data, { openConversationId });
      if (!result.matched) {
        void load('poll');
        return;
      }
      chatsRef.current = result.chats;
      setChats(result.chats);
    },
    [load],
  );

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
    waitingCount,
    indexRebuild,
    refresh: () => void load('refresh'),
    loadMore,
    reloadQuiet: () => void load('poll'),
    applyNewMessage,
  };
}
