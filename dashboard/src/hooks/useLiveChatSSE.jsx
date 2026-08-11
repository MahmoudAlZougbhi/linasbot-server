import { useEffect } from "react";
import { getApiBaseUrl } from "../utils/apiBaseUrl";
import {
  FALLBACK_POLL_INTERVAL_MS,
  HEARTBEAT_WATCHDOG_INTERVAL_MS,
  SSE_STALE_THRESHOLD_MS,
  attachLiveChatSSEListeners,
  mergeFetchedWithRecentLocal,
} from "./useLiveChatSSE.helpers";

/**
 * @param {{
 *   enabled: boolean;
 *   isMountedRef: import('react').MutableRefObject<boolean>;
 *   useMockDataRef: import('react').MutableRefObject<boolean>;
 *   activeConversationsRef: import('react').MutableRefObject<LiveChatConversation[] | null | undefined>;
 *   selectedConversationRef: import('react').MutableRefObject<SelectedConversation | null | undefined>;
 *   debouncedSearchRef: import('react').MutableRefObject<string>;
 *   getUnifiedChats: (search: string, page: number, pageSize: number) => Promise<{ success?: boolean; chats?: LiveChatConversation[]; has_more?: boolean }>;
 *   getWaitingQueue?: () => Promise<{ success?: boolean; queue?: QueueItem[] }>;
 *   applyWaitingQueue?: (response: { success?: boolean; queue?: QueueItem[] }) => void;
 *   chatListPageSize?: number;
 *   fetchConversationMessages: (
 *     userId: string,
 *     conversationId: string,
 *     days?: number,
 *     before?: string | null,
 *     day_window?: number,
 *     limit?: number
 *   ) => Promise<{ messages?: LiveChatMessage[] }>;
 *   setActiveConversations: import('react').Dispatch<import('react').SetStateAction<LiveChatConversation[]>> | ((conversations: LiveChatConversation[]) => void);
 *   setNewConversationIds: import('react').Dispatch<import('react').SetStateAction<Set<string>>>;
 *   setLastRefreshTime: import('react').Dispatch<import('react').SetStateAction<Date | null>>;
 *   setIsRefreshing: import('react').Dispatch<import('react').SetStateAction<boolean>>;
 *   setSelectedConversation: import('react').Dispatch<import('react').SetStateAction<SelectedConversation | null>>;
 *   updateChatListLocally?: (convId: string | undefined, userId: string | undefined, message: LiveChatMessage) => void;
 *   messageCacheRef?: import('react').MutableRefObject<Map<string, { messages: LiveChatMessage[]; hasMore?: boolean; cachedAt?: number; isPartial?: boolean }>>;
 *   hasMoreMessagesRef?: import('react').MutableRefObject<boolean>;
 *   setIsLoading?: import('react').Dispatch<import('react').SetStateAction<boolean>>;
 *   setHasMoreChats?: import('react').Dispatch<import('react').SetStateAction<boolean>>;
 *   setChatPage?: import('react').Dispatch<import('react').SetStateAction<number>>;
 *   onOperatorMessageCached?: (userId: string, convId: string, message: LiveChatMessage) => void;
 * }} params
 */
export const useLiveChatSSE = ({
  enabled,
  isMountedRef,
  useMockDataRef,
  activeConversationsRef,
  selectedConversationRef,
  debouncedSearchRef,
  getUnifiedChats,
  getWaitingQueue,
  applyWaitingQueue,
  chatListPageSize = 50,
  fetchConversationMessages,
  setActiveConversations,
  setNewConversationIds,
  setLastRefreshTime,
  setIsRefreshing,
  setSelectedConversation,
  updateChatListLocally,
  messageCacheRef,
  hasMoreMessagesRef,
  setIsLoading,
  setHasMoreChats,
  setChatPage,
  onOperatorMessageCached,
}) => {
  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    /** @type {EventSource | null} */
    let eventSource = null;
    /** @type {ReturnType<typeof setTimeout> | null} */
    let reconnectTimeout = null;
    /** @type {ReturnType<typeof setInterval> | null} */
    let fallbackInterval = null;
    /** @type {ReturnType<typeof setTimeout> | null} */
    let clearNewBadgeTimeout = null;
    /** @type {ReturnType<typeof setInterval> | null} */
    let heartbeatWatchdog = null;
    let refreshingFallback = false;

    /** @type {{
     *   reconnectAttempt: number;
     *   handlingNewMessageEvent: boolean;
     *   lastRefreshAt: number;
     *   debouncedRefreshScheduled: boolean;
     *   lastEventAt: number;
     * }} */
    const state = {
      reconnectAttempt: 0,
      handlingNewMessageEvent: false,
      lastRefreshAt: 0,
      debouncedRefreshScheduled: false,
      lastEventAt: Date.now(),
    };

    const clearNewBadgesSoon = () => {
      if (clearNewBadgeTimeout) {
        clearTimeout(clearNewBadgeTimeout);
      }
      clearNewBadgeTimeout = setTimeout(() => setNewConversationIds(new Set()), 10000);
    };

    /**
     * @param {{
     *   preferredConversations?: LiveChatConversation[] | null;
     *   announceNewIds?: Set<string> | null;
     *   total?: number | null;
     *   hasMore?: boolean | null;
     * }} [options]
     */
    const refreshChats = async ({
      preferredConversations = null,
      announceNewIds = null,
      total = null,
      hasMore = null,
    } = {}) => {
      if (!isMountedRef.current) return null;
      const searchTerm = debouncedSearchRef.current;
      /** @type {LiveChatConversation[] | null} */
      let conversations = null;
      /** @type {boolean | null} */
      let hasMoreValue = hasMore;
      if (!searchTerm && preferredConversations != null && Array.isArray(preferredConversations)) {
        conversations = preferredConversations;
        if (total != null) hasMoreValue = total > conversations.length;
      }
      if (conversations == null) {
        const chatsResponse = await getUnifiedChats(searchTerm, 1, chatListPageSize);
        if (!isMountedRef.current) return null;
        conversations =
          chatsResponse?.success && chatsResponse?.chats ? chatsResponse.chats : preferredConversations;
        if (chatsResponse?.success) hasMoreValue = chatsResponse.has_more ?? false;
      }
      if (!conversations) return null;

      const selected = selectedConversationRef.current;
      if (selected?.conversation) {
        const alreadyInList = conversations.some(
          (/** @type {LiveChatConversation} */ c) =>
            c.conversation_id === selected.conversation.conversation_id &&
            c.user_id === selected.conversation.user_id
        );
        if (!alreadyInList) {
          conversations = [selected.conversation, ...conversations];
        }
      }

      const previousIds = new Set(
        (activeConversationsRef.current || []).map(
          (/** @type {LiveChatConversation} */ conversation) => conversation.conversation_id
        )
      );
      const calculatedNewIds = new Set(
        conversations
          .filter((/** @type {LiveChatConversation} */ conversation) => !previousIds.has(conversation.conversation_id))
          .map((/** @type {LiveChatConversation} */ conversation) => conversation.conversation_id)
      );

      const newIds = announceNewIds || calculatedNewIds;
      setActiveConversations(conversations);
      setLastRefreshTime(new Date());
      setNewConversationIds(newIds);
      if (newIds.size > 0) {
        clearNewBadgesSoon();
      }

      if (total != null && setIsLoading) setIsLoading(false);
      if (hasMoreValue != null && setHasMoreChats) setHasMoreChats(hasMoreValue);
      if (getWaitingQueue && applyWaitingQueue) {
        getWaitingQueue()
          .then((/** @type {{ success?: boolean; queue?: QueueItem[] }} */ queueResponse) => {
            if (!isMountedRef.current) return;
            if (queueResponse?.success && queueResponse?.queue) {
              applyWaitingQueue(queueResponse);
            }
          })
          .catch(() => {});
      }
      return conversations;
    };

    const refreshSelectedConversation = async () => {
      if (!isMountedRef.current) return;
      const selected = selectedConversationRef.current;
      if (!selected?.conversation) return;
      try {
        const { messages } = await fetchConversationMessages(
          selected.conversation.user_id,
          selected.conversation.conversation_id,
          1,
          null,
          0,
          50
        );
        if (!isMountedRef.current || !messages?.length) return;
        const mergedMessages = mergeFetchedWithRecentLocal(
          messages,
          selectedConversationRef.current?.history || []
        );
        if (messageCacheRef?.current) {
          const cacheKey = `${selected.conversation.user_id}_${selected.conversation.conversation_id}`;
          const existing = messageCacheRef.current.get(cacheKey);
          messageCacheRef.current.set(cacheKey, {
            messages: mergedMessages,
            hasMore: existing?.hasMore ?? true,
            cachedAt: Date.now(),
            isPartial: true,
          });
        }
        setSelectedConversation((/** @type {SelectedConversation | null} */ previous) => {
          if (!previous) return previous;
          return { ...previous, history: mergedMessages };
        });
      } catch {
        // Silent fail: user can manually refresh
      }
    };

    /** @param {Record<string, unknown>} eventData */
    const refreshSelectedConversationIfMatched = async (eventData) => {
      const selected = selectedConversationRef.current;
      if (!selected || !isMountedRef.current) return;

      const hasConversationId = Boolean(eventData?.conversation_id);
      const isSameConversation = hasConversationId
        ? selected.conversation.conversation_id === eventData.conversation_id
        : selected.conversation.user_id === eventData.user_id;
      if (!isSameConversation) return;

      try {
        const { messages } = await fetchConversationMessages(
          selected.conversation.user_id,
          selected.conversation.conversation_id,
          1,
          null,
          0,
          50
        );
        if (!isMountedRef.current || !messages?.length) return;
        const mergedMessages = mergeFetchedWithRecentLocal(
          messages,
          selectedConversationRef.current?.history || []
        );
        if (messageCacheRef?.current) {
          const cacheKey = `${selected.conversation.user_id}_${selected.conversation.conversation_id}`;
          const existing = messageCacheRef.current.get(cacheKey);
          messageCacheRef.current.set(cacheKey, {
            messages: mergedMessages,
            hasMore: existing?.hasMore ?? true,
            cachedAt: Date.now(),
            isPartial: true,
          });
        }
        setSelectedConversation((/** @type {SelectedConversation | null} */ previous) => {
          if (!previous) return previous;
          return { ...previous, history: mergedMessages };
        });
      } catch {
        // Silent fail for SSE refresh - user can manually reload
      }
    };

    const startFallbackPolling = () => {
      if (fallbackInterval) return;
      fallbackInterval = setInterval(async () => {
        if (!isMountedRef.current || useMockDataRef.current) return;
        try {
          await refreshChats();
        } catch {
          // Keep fallback silent to avoid noisy toasts during transient outages.
        }
      }, FALLBACK_POLL_INTERVAL_MS);
    };

    const stopFallbackPolling = () => {
      if (!fallbackInterval) return;
      clearInterval(fallbackInterval);
      fallbackInterval = null;
    };

    const connectSSE = () => {
      if (useMockDataRef.current) return;

      const baseUrl = getApiBaseUrl();
      eventSource = new EventSource(`${baseUrl}/api/live-chat/events`);

      attachLiveChatSSEListeners(eventSource, {
        isMountedRef,
        useMockDataRef,
        activeConversationsRef,
        selectedConversationRef,
        debouncedSearchRef,
        messageCacheRef,
        hasMoreMessagesRef,
        setActiveConversations,
        setNewConversationIds,
        setLastRefreshTime,
        setIsRefreshing,
        setSelectedConversation,
        setIsLoading,
        updateChatListLocally,
        onOperatorMessageCached,
        refreshChats,
        refreshSelectedConversation,
        refreshSelectedConversationIfMatched,
        startFallbackPolling,
        stopFallbackPolling,
        state,
      });

      if (!heartbeatWatchdog) {
        heartbeatWatchdog = setInterval(async () => {
          if (!isMountedRef.current || useMockDataRef.current) return;
          const elapsed = Date.now() - state.lastEventAt;
          if (elapsed < SSE_STALE_THRESHOLD_MS || refreshingFallback) return;
          refreshingFallback = true;
          try {
            await refreshChats();
            const selected = selectedConversationRef.current;
            if (selected && !selected.history?.length) {
              await refreshSelectedConversation();
            }
          } finally {
            refreshingFallback = false;
          }
        }, HEARTBEAT_WATCHDOG_INTERVAL_MS);
      }

      eventSource.onerror = () => {
        if (eventSource) {
          eventSource.close();
        }
        startFallbackPolling();
        state.reconnectAttempt += 1;
        const reconnectDelayMs = Math.min(30000, 1000 * Math.min(state.reconnectAttempt, 10));
        if (process.env.NODE_ENV === "development") {
          console.log("[SSE] error, reconnect in", reconnectDelayMs, "ms, attempt", state.reconnectAttempt);
        }
        reconnectTimeout = setTimeout(connectSSE, reconnectDelayMs);
      };
    };

    connectSSE();

    return () => {
      if (eventSource) {
        eventSource.close();
      }
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      if (heartbeatWatchdog) {
        clearInterval(heartbeatWatchdog);
      }
      if (clearNewBadgeTimeout) {
        clearTimeout(clearNewBadgeTimeout);
      }
      stopFallbackPolling();
    };
  }, [
    applyWaitingQueue,
    getWaitingQueue,
    hasMoreMessagesRef,
    messageCacheRef,
    onOperatorMessageCached,
    activeConversationsRef,
    chatListPageSize,
    debouncedSearchRef,
    enabled,
    fetchConversationMessages,
    getUnifiedChats,
    isMountedRef,
    selectedConversationRef,
    setActiveConversations,
    setChatPage,
    setHasMoreChats,
    setIsLoading,
    setIsRefreshing,
    setLastRefreshTime,
    setNewConversationIds,
    setSelectedConversation,
    updateChatListLocally,
    useMockDataRef,
  ]);
};
