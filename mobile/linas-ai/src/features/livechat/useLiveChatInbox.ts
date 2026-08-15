import { useCallback, useEffect, useRef, useState } from 'react';

import { classifyLiveChatError, fetchUnifiedChats, setOperatorAvailable } from './liveChatApi';
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

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [search]);

  const load = useCallback(
    async (mode: 'initial' | 'refresh' | 'poll' = 'initial') => {
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
        const rows = data.chats ?? [];
        const rebuild = Boolean(data.requires_index_rebuild || data.index_empty);
        // Show whatever rows exist. success:false with no chats is a load error, not empty —
        // unless the server signaled an empty index / rebuild (not a hard outage).
        if (rows.length === 0 && data.success === false && !rebuild) {
          throw new Error(data.error || 'Could not load conversations.');
        }
        setChats(rows);
        setHasMore(Boolean(data.has_more));
        setNextCursor(data.next_cursor ?? null);
        setTotal(typeof data.total === 'number' ? data.total : rows.length);
        setIndexRebuild(rebuild);
        setError(null);
        setErrorKind(null);
      } catch (err) {
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
        setLoading(false);
        setRefreshing(false);
      }
    },
    [debouncedSearch, filter, channel],
  );

  const loadMore = useCallback(async () => {
    if (!hasMore || loadingMore) return;
    setLoadingMore(true);
    try {
      const data = await fetchUnifiedChats({
        search: debouncedSearch,
        page: 1,
        pageSize: PAGE_SIZE,
        cursor: nextCursor,
        filter,
        channel,
      });
      setChats((prev) => {
        const seen = new Set(prev.map((c) => c.conversation_id));
        const merged = [...prev];
        for (const c of data.chats) {
          if (!seen.has(c.conversation_id)) merged.push(c);
        }
        return merged;
      });
      setHasMore(Boolean(data.has_more));
      setNextCursor(data.next_cursor ?? null);
    } catch {
      // Keep existing list.
    } finally {
      setLoadingMore(false);
    }
  }, [debouncedSearch, filter, channel, hasMore, loadingMore, nextCursor]);

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
