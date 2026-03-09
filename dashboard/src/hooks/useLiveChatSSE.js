import { useEffect } from "react";
import { getApiBaseUrl } from "../utils/apiBaseUrl";

const FULL_REFRESH_COOLDOWN_MS = 45000; // At most one full refresh every 45s
const FULL_REFRESH_DELAY_MS = 1500;
const FALLBACK_POLL_INTERVAL_MS = 30000;
const SSE_STALE_THRESHOLD_MS = 90000;
const HEARTBEAT_WATCHDOG_INTERVAL_MS = 30000;

export const useLiveChatSSE = ({
  enabled,
  isMountedRef,
  useMockDataRef,
  activeConversationsRef,
  selectedConversationRef,
  debouncedSearchRef,
  getUnifiedChats,
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

    let eventSource = null;
    let reconnectTimeout = null;
    let fallbackInterval = null;
    let clearNewBadgeTimeout = null;
    let reconnectAttempt = 0;
    let handlingNewMessageEvent = false;
    let lastRefreshAt = 0;
    let debouncedRefreshScheduled = false;
    let lastEventAt = Date.now();
    let heartbeatWatchdog = null;
    let refreshingFallback = false;

    const clearNewBadgesSoon = () => {
      if (clearNewBadgeTimeout) {
        clearTimeout(clearNewBadgeTimeout);
      }
      clearNewBadgeTimeout = setTimeout(() => setNewConversationIds(new Set()), 10000);
    };

    const refreshChats = async ({
      preferredConversations = null,
      announceNewIds = null,
      total = null,
      hasMore = null,
    } = {}) => {
      if (!isMountedRef.current) return null;
      const searchTerm = debouncedSearchRef.current;
      let conversations = null;
      let hasMoreValue = hasMore;
      // Use SSE payload when no search - single Firestore scan on open (no duplicate API call)
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

      // Keep selected conversation in the list so it doesn't disappear from "With operator" / Active when refetching
      const selected = selectedConversationRef.current;
      if (selected?.conversation) {
        const alreadyInList = conversations.some(
          (c) => c.conversation_id === selected.conversation.conversation_id && c.user_id === selected.conversation.user_id
        );
        if (!alreadyInList) {
          conversations = [selected.conversation, ...conversations];
        }
      }

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

      if (total != null && setIsLoading) setIsLoading(false);
      if (hasMoreValue != null && setHasMoreChats) setHasMoreChats(hasMoreValue);
      if (setChatPage) setChatPage(1);

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
        if (messageCacheRef?.current) {
          const cacheKey = `${selected.conversation.user_id}_${selected.conversation.conversation_id}`;
          messageCacheRef.current.set(cacheKey, {
            messages,
            hasMore: false,
            cachedAt: Date.now(),
          });
        }
        setSelectedConversation((previous) => {
          if (!previous) return previous;
          return { ...previous, history: messages };
        });
      } catch {
        // Silent fail: user can manually refresh
      }
    };

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
        if (messageCacheRef?.current) {
          const cacheKey = `${selected.conversation.user_id}_${selected.conversation.conversation_id}`;
          messageCacheRef.current.set(cacheKey, {
            messages,
            hasMore: false,
            cachedAt: Date.now(),
          });
        }
        setSelectedConversation((previous) => {
          if (!previous) return previous;
          return { ...previous, history: messages };
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
        } catch (error) {
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

      eventSource.onopen = () => {
        reconnectAttempt = 0;
        stopFallbackPolling();
        lastEventAt = Date.now();
        if (process.env.NODE_ENV === "development") {
          console.log("[SSE] connected");
        }
      };

      eventSource.addEventListener("conversations", async (event) => {
        if (!isMountedRef.current) return;
        try {
          const data = JSON.parse(event.data || "{}");
          lastEventAt = Date.now();
          const conversations = Array.isArray(data.conversations) ? data.conversations : null;
          const total = typeof data.total === "number" ? data.total : (conversations?.length || 0);
          await refreshChats({
            preferredConversations: conversations,
            total,
          });
          // List only: stop loading; do not auto-select so chat messages load only when user clicks
          if (setIsLoading) setIsLoading(false);
        } catch (error) {
          console.error("SSE conversations parse error:", error);
          if (setIsLoading) setIsLoading(false);
        }
      });

      eventSource.addEventListener("new_message", async (event) => {
        if (!isMountedRef.current) return;
        if (handlingNewMessageEvent) return;
        handlingNewMessageEvent = true;
        try {
          const data = JSON.parse(event.data || "{}");
          lastEventAt = Date.now();
          const selected = selectedConversationRef.current;
          const convId = data?.conversation_id;
          const userId = data?.user_id;
          const message = data?.message;

          // 1) If message for open conversation: append immediately (no API call)
          const msgId = message?.message_id;
          const isMatch =
            selected &&
            ((convId && selected.conversation?.conversation_id === convId) ||
              (userId && selected.conversation?.user_id === userId));
          if (isMatch && message && typeof message === "object" && message.timestamp) {
            setSelectedConversation((prev) => {
              if (!prev || !prev.history) return prev;
              const content = String(message.content || message.text || "").trim();
              const exists = prev.history.some((m) => {
                if (msgId && m.message_id) return m.message_id === msgId;
                // Dedupe operator messages: same content within 15s (handles race with manual append)
                if (content && String(m.content || m.text || "").trim() === content) {
                  const mTs = m.timestamp ? new Date(m.timestamp).getTime() : 0;
                  const msgTs = message.timestamp ? new Date(message.timestamp).getTime() : 0;
                  if (Math.abs(mTs - msgTs) < 15000) return true;
                }
                return (
                  m.timestamp === message.timestamp &&
                  String(m.content || m.text || "") === String(message.content || message.text || "")
                );
              });
              if (exists) return prev;
              const updatedHistory = [...prev.history, message];
              // Update message cache so switching back shows the new message
              if (messageCacheRef?.current && prev.conversation) {
                const cacheKey = `${prev.conversation.user_id}_${prev.conversation.conversation_id}`;
                const existing = messageCacheRef.current.get(cacheKey);
                messageCacheRef.current.set(cacheKey, {
                  messages: updatedHistory,
                  hasMore: existing?.hasMore ?? (hasMoreMessagesRef?.current ?? false),
                  cachedAt: Date.now(),
                });
                if (onOperatorMessageCached && (message.role === "operator" || message.is_user === false)) {
                  onOperatorMessageCached(prev.conversation.user_id, prev.conversation.conversation_id, message);
                }
              }
              return { ...prev, history: updatedHistory };
            });
            if (process.env.NODE_ENV === "development") {
              console.log("[SSE] new_message merged (instant append)", { convId, msgId });
            }
          }

          // 2) Update chat list locally: move to top, update last_message + last_activity (no /unified-chats call)
          if (updateChatListLocally && message && (convId || userId)) {
            updateChatListLocally(convId, userId, message);
          }

          // 2b) Update message cache for this conversation when not viewing it (so switch-back shows new message)
          if (messageCacheRef?.current && message && convId && userId) {
            const cacheKey = `${userId}_${convId}`;
            const existing = messageCacheRef.current.get(cacheKey);
            if (existing?.messages?.length) {
              const content = String(message.content || message.text || "").trim();
              const msgId = message?.message_id;
              const exists = existing.messages.some((m) => {
                if (msgId && m.message_id) return m.message_id === msgId;
                if (content && String(m.content || m.text || "").trim() === content) {
                  const mTs = m.timestamp ? new Date(m.timestamp).getTime() : 0;
                  const msgTs = message.timestamp ? new Date(message.timestamp).getTime() : 0;
                  if (Math.abs(mTs - msgTs) < 15000) return true;
                }
                return false;
              });
              if (!exists) {
                messageCacheRef.current.set(cacheKey, {
                  messages: [...existing.messages, message],
                  hasMore: existing.hasMore,
                  cachedAt: Date.now(),
                });
                if (onOperatorMessageCached && (message.role === "operator" || message.is_user === false)) {
                  onOperatorMessageCached(userId, convId, message);
                }
              }
            }
          }

          // 3) Very low-frequency full refresh (safety net only; local merge is primary path)
          const now = Date.now();
          if (
            !debouncedSearchRef.current &&
            now - lastRefreshAt >= FULL_REFRESH_COOLDOWN_MS &&
            !debouncedRefreshScheduled
          ) {
            debouncedRefreshScheduled = true;
            setTimeout(async () => {
              if (!isMountedRef.current) return;
              debouncedRefreshScheduled = false;
              lastRefreshAt = Date.now();
              setIsRefreshing(true);
              try {
                await refreshChats();
              } finally {
                setIsRefreshing(false);
              }
            }, FULL_REFRESH_DELAY_MS);
          }

          // 4) If viewing a different conversation, fetch its messages (no full list refresh)
          if (!isMatch || !message) {
            await refreshSelectedConversationIfMatched(data);
          }
        } catch (error) {
          debouncedRefreshScheduled = false;
          setIsRefreshing(false);
          console.error("SSE new_message handler error:", error);
        } finally {
          handlingNewMessageEvent = false;
        }
      });

      eventSource.addEventListener("message_updated", (event) => {
        if (!isMountedRef.current) return;
        try {
          const data = JSON.parse(event.data || "{}");
          lastEventAt = Date.now();
          const selected = selectedConversationRef.current;
          const convId = data?.conversation_id;
          const message = data?.message;
          const msgId = message?.message_id;
          const isMatch =
            selected &&
            convId &&
            selected.conversation?.conversation_id === convId &&
            message &&
            msgId;
          if (isMatch) {
            setSelectedConversation((prev) => {
              if (!prev || !prev.history) return prev;
              return {
                ...prev,
                history: prev.history.map((m) =>
                  (m.message_id || m.id) === msgId
                    ? { ...m, content: message.content ?? message.text, text: message.text ?? message.content }
                    : m
                ),
              };
            });
          }
        } catch (error) {
          console.error("SSE message_updated handler error:", error);
        }
      });

      eventSource.addEventListener("new_conversation", (event) => {
        if (!isMountedRef.current) return;
        try {
          const data = JSON.parse(event.data || "{}");
          lastEventAt = Date.now();
          const convId = data?.conversation_id;
          const userId = data?.user_id;
          const phone = data?.phone || "";
          const name = data?.name || "Unknown";
          if (convId && userId) {
            // Add new conversation locally (no /unified-chats call)
            const now = new Date().toISOString();
            setActiveConversations((prev) => {
              const exists = prev.some((c) => c.conversation_id === convId || c.user_id === userId);
              if (exists) return prev;
              const newEntry = {
                user_id: userId,
                conversation_id: convId,
                user_name: name,
                user_phone: phone,
                last_message: { content: "", is_user: true, timestamp: now },
                last_activity: now,
                status: "bot",
                is_live: true,
              };
              return [newEntry, ...prev];
            });
            setNewConversationIds((prev) => new Set([...prev, convId]));
            setLastRefreshTime(new Date());
          }
        } catch (error) {
          console.error("SSE new_conversation handler error:", error);
        }
      });

      eventSource.addEventListener("heartbeat", () => {
        // No-op, this event is only for keep-alive.
        lastEventAt = Date.now();
      });

      if (!heartbeatWatchdog) {
        heartbeatWatchdog = setInterval(async () => {
          if (!isMountedRef.current || useMockDataRef.current) return;
          const elapsed = Date.now() - lastEventAt;
          if (elapsed < SSE_STALE_THRESHOLD_MS || refreshingFallback) return;
          refreshingFallback = true;
          try {
            // SSE is stale; do a conservative reconciliation fetch.
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
      if (heartbeatWatchdog) {
        clearInterval(heartbeatWatchdog);
      }
      if (clearNewBadgeTimeout) {
        clearTimeout(clearNewBadgeTimeout);
      }
      stopFallbackPolling();
    };
  }, [
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
