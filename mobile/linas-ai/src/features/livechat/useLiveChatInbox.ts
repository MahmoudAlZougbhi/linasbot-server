import { useCallback, useEffect, useRef, useState } from 'react';

import { cacheGet, cacheSet, dedupeFetch, isCacheFresh } from '../../cache/queryCache';
import { queryKeys } from '../../cache/queryKeys';
import { QUERY_TTL } from '../../cache/queryTtl';
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

type InboxSnapshot = {
  chats: LiveChatItem[];
  total: number;
  waitingCount: number;
  hasMore: boolean;
  nextCursor: string | null;
  indexRebuild: boolean;
};

export function useLiveChatInbox(enabled = true) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<InboxFilter>('all');
  const [channel, setChannel] = useState<ChannelFilter>('all');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const inboxKey = queryKeys.liveChatInbox(filter, channel, debouncedSearch);
  const cached = enabled ? cacheGet<InboxSnapshot>(inboxKey) : null;
  const [chats, setChats] = useState<LiveChatItem[]>(cached?.data.chats ?? []);
  const [loading, setLoading] = useState(enabled && !cached);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(!enabled || Boolean(cached));
  const hasLoadedOnceRef = useRef(!enabled || Boolean(cached));
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorKind, setErrorKind] = useState<'forbidden' | 'auth' | 'other' | null>(null);
  const [hasMore, setHasMore] = useState(cached?.data.hasMore ?? false);
  const [nextCursor, setNextCursor] = useState<string | null>(cached?.data.nextCursor ?? null);
  const [total, setTotal] = useState(cached?.data.total ?? 0);
  const [indexRebuild, setIndexRebuild] = useState(cached?.data.indexRebuild ?? false);
  const [waitingCount, setWaitingCount] = useState(cached?.data.waitingCount ?? 0);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
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
    async (mode: 'initial' | 'refresh' | 'poll' | 'event' = 'initial') => {
      const requestId = ++requestIdRef.current;
      const key = queryKeys.liveChatInbox(filter, channel, debouncedSearch);
      const hit = cacheGet<InboxSnapshot>(key);
      if (hit) {
        setChats(hit.data.chats);
        setTotal(hit.data.total);
        setWaitingCount(hit.data.waitingCount);
        setHasMore(hit.data.hasMore);
        setNextCursor(hit.data.nextCursor);
        nextCursorRef.current = hit.data.nextCursor;
        hasMoreRef.current = hit.data.hasMore;
        setIndexRebuild(hit.data.indexRebuild);
        hasLoadedOnceRef.current = true;
        setHasLoadedOnce(true);
        setLoading(false);
      }
      if (
        (mode === 'poll' || mode === 'initial') &&
        hasLoadedOnceRef.current &&
        isCacheFresh(key, QUERY_TTL.liveChatInbox)
      ) {
        return;
      }
      if (mode === 'initial' && !hasLoadedOnceRef.current) setLoading(true);
      if (mode === 'refresh') setRefreshing(true);
      try {
        const data = await dedupeFetch(key, () =>
          fetchUnifiedChats({
            search: debouncedSearch,
            page: 1,
            pageSize: PAGE_SIZE,
            filter,
            channel,
          }),
        );
        if (requestId !== requestIdRef.current) return;
        const rows = data.chats ?? [];
        const rebuild = Boolean(data.requires_index_rebuild || data.index_empty);
        // Show whatever rows exist. success:false with no chats is a load error, not empty —
        // unless the server signaled an empty index / rebuild (not a hard outage).
        if (rows.length === 0 && data.success === false && !rebuild) {
          throw new Error(data.error || 'Could not load conversations.');
        }
        const mergePoll = (mode === 'poll' || mode === 'event') && paginatedBeyondFirstRef.current;
        if (mergePoll) {
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
        cacheSet(key, {
          chats: mergePoll ? chatsRef.current : rows,
          total: typeof data.total === 'number' ? data.total : rows.length,
          waitingCount: waitingCountFromResponse(data, filter, rows),
          hasMore: Boolean(data.has_more),
          nextCursor: data.next_cursor ?? null,
          indexRebuild: rebuild,
        });
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        if (mode !== 'poll' && mode !== 'event') {
          const kind = classifyLiveChatError(err);
          setErrorKind(kind);
          setError(
            kind === 'forbidden'
              ? 'You do not have permission for Live Chat.'
              : err instanceof Error
                ? err.message
                : 'Could not load conversations.',
          );
          if (mode === 'initial' && chatsRef.current.length === 0) setChats([]);
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
        void load('event');
        return;
      }
      chatsRef.current = result.chats;
      setChats(result.chats);
      cacheSet(queryKeys.liveChatInbox(filter, channel, debouncedSearch), {
        chats: result.chats,
        total,
        waitingCount,
        hasMore,
        nextCursor,
        indexRebuild,
      });
    },
    [load, filter, channel, debouncedSearch, total, waitingCount, hasMore, nextCursor, indexRebuild],
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
    reloadFromEvent: () => void load('event'),
    catchUpIfStale: () => {
      const key = queryKeys.liveChatInbox(filter, channel, debouncedSearch);
      if (!isCacheFresh(key, QUERY_TTL.liveChatInbox)) void load('poll');
    },
    applyNewMessage,
  };
}
