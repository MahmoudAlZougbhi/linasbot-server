import { useEffect } from "react";
import { getApiBaseUrl } from "../utils/apiBaseUrl";

export const useLiveChatSSE = ({
  enabled,
  isMountedRef,
  useMockDataRef,
  activeConversationsRef,
  selectedConversationRef,
  debouncedSearchRef,
  getUnifiedChats,
  fetchConversationMessages,
  setActiveConversations,
  setNewConversationIds,
  setLastRefreshTime,
  setIsRefreshing,
  setSelectedConversation,
}) => {
  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    let eventSource = null;
    let reconnectTimeout = null;
    let fallbackInterval = null;
    let clearNewBadgeTimeout = null;
    let reconnectAttempt = 0;
    let handlingNewMessageEvent = false;

    const clearNewBadgesSoon = () => {
      if (clearNewBadgeTimeout) {
        clearTimeout(clearNewBadgeTimeout);
      }
      clearNewBadgeTimeout = setTimeout(() => setNewConversationIds(new Set()), 10000);
    };

    const refreshChats = async ({ preferredConversations = null, announceNewIds = null } = {}) => {
      if (!isMountedRef.current) return null;
      const searchTerm = debouncedSearchRef.current;
      const chatsResponse = await getUnifiedChats(searchTerm, 1, 30);
      if (!isMountedRef.current) return null;

      const conversations =
        chatsResponse?.success && chatsResponse?.chats ? chatsResponse.chats : preferredConversations;
      if (!conversations) return null;

      const previousIds = new Set(
        (activeConversationsRef.current || []).map((conversation) => conversation.conversation_id)
      );
      const calculatedNewIds = new Set(
        conversations
          .filter((conversation) => !previousIds.has(conversation.conversation_id))
          .map((conversation) => conversation.conversation_id)
      );

      const newIds = announceNewIds || calculatedNewIds;
      setActiveConversations(conversations);
      setLastRefreshTime(new Date());
      setNewConversationIds(newIds);
      if (newIds.size > 0) {
        clearNewBadgesSoon();
      }

      return conversations;
    };

    const refreshSelectedConversationIfMatched = async (eventData) => {
      const selected = selectedConversationRef.current;
      if (!selected || !isMountedRef.current) return;

      const hasConversationId = Boolean(eventData?.conversation_id);
      const isSameConversation = hasConversationId
        ? selected.conversation.conversation_id === eventData.conversation_id
        : selected.conversation.user_id === eventData.user_id;
      if (!isSameConversation) return;

      const { messages } = await fetchConversationMessages(
        selected.conversation.user_id,
        selected.conversation.conversation_id,
        1,
        null,
        50
      );
      if (!isMountedRef.current || !messages?.length) return;

      setSelectedConversation((previous) => {
        if (!previous) return previous;
        return { ...previous, history: messages };
      });
    };

    const startFallbackPolling = () => {
      if (fallbackInterval) return;
      fallbackInterval = setInterval(async () => {
        if (!isMountedRef.current || useMockDataRef.current) return;
        try {
          await refreshChats();
        } catch (error) {
          // Keep fallback silent to avoid noisy toasts during transient outages.
        }
      }, 10000);
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

      eventSource.onopen = () => {
        reconnectAttempt = 0;
        stopFallbackPolling();
        if (process.env.NODE_ENV === "development") {
          console.log("[SSE] connected");
        }
      };

      eventSource.addEventListener("conversations", async (event) => {
        if (!isMountedRef.current) return;
        try {
          const data = JSON.parse(event.data || "{}");
          const conversations = Array.isArray(data.conversations) ? data.conversations : null;
          await refreshChats({ preferredConversations: conversations });
        } catch (error) {
          console.error("SSE conversations parse error:", error);
        }
      });

      eventSource.addEventListener("new_message", async (event) => {
        if (!isMountedRef.current) return;
        if (handlingNewMessageEvent) return;
        handlingNewMessageEvent = true;
        try {
          const data = JSON.parse(event.data || "{}");
          const selected = selectedConversationRef.current;
          const convId = data?.conversation_id;
          const userId = data?.user_id;
          const message = data?.message;

          // Dedupe and merge by message_id (never timestamp+content - unstable for rapid messages)
          const msgId = message?.message_id;

          const isMatch =
            selected &&
            ((convId && selected.conversation?.conversation_id === convId) ||
              (userId && selected.conversation?.user_id === userId));
          if (isMatch && message && typeof message === "object" && message.timestamp) {
            setSelectedConversation((prev) => {
              if (!prev || !prev.history) return prev;
              // Dedupe by message_id; fallback to content+ts only when message_id absent (legacy)
              const exists = prev.history.some((m) => {
                if (msgId && m.message_id) return m.message_id === msgId;
                if (msgId && !m.message_id) return false;
                return (
                  m.timestamp === message.timestamp &&
                  String(m.content || m.text || "") === String(message.content || message.text || "")
                );
              });
              if (exists) return prev;
              return { ...prev, history: [...prev.history, message] };
            });
            if (process.env.NODE_ENV === "development") {
              console.log("[SSE] new_message merged", { convId, msgId });
            }
          }

          setIsRefreshing(true);
          refreshChats().finally(() => setIsRefreshing(false));

          if (!isMatch || !message) {
            await refreshSelectedConversationIfMatched(data);
          }
        } catch (error) {
          setIsRefreshing(false);
          console.error("SSE new_message handler error:", error);
        } finally {
          handlingNewMessageEvent = false;
        }
      });

      eventSource.addEventListener("new_conversation", async (event) => {
        if (!isMountedRef.current) return;
        try {
          const data = JSON.parse(event.data || "{}");
          const announcedId = data?.conversation_id;
          const newIds = announcedId ? new Set([announcedId]) : new Set();
          await refreshChats({ announceNewIds: newIds });
        } catch (error) {
          console.error("SSE new_conversation handler error:", error);
        }
      });

      eventSource.addEventListener("heartbeat", () => {
        // No-op, this event is only for keep-alive.
      });

      eventSource.onerror = () => {
        if (eventSource) {
          eventSource.close();
        }
        startFallbackPolling();
        reconnectAttempt += 1;
        const reconnectDelayMs = Math.min(30000, 1000 * Math.min(reconnectAttempt, 10));
        if (process.env.NODE_ENV === "development") {
          console.log("[SSE] error, reconnect in", reconnectDelayMs, "ms, attempt", reconnectAttempt);
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
      if (clearNewBadgeTimeout) {
        clearTimeout(clearNewBadgeTimeout);
      }
      stopFallbackPolling();
    };
  }, [
    activeConversationsRef,
    debouncedSearchRef,
    enabled,
    fetchConversationMessages,
    getUnifiedChats,
    isMountedRef,
    selectedConversationRef,
    setActiveConversations,
    setIsRefreshing,
    setLastRefreshTime,
    setNewConversationIds,
    setSelectedConversation,
    useMockDataRef,
  ]);
};
