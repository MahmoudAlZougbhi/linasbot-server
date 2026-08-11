export const FULL_REFRESH_COOLDOWN_MS = 45000; // At most one full refresh every 45s
export const FULL_REFRESH_DELAY_MS = 1500;
export const FALLBACK_POLL_INTERVAL_MS = 30000;
export const SSE_STALE_THRESHOLD_MS = 90000;
export const HEARTBEAT_WATCHDOG_INTERVAL_MS = 30000;

/** @param {LiveChatMessage[]} [fetchedMessages] @param {LiveChatMessage[]} [currentHistory] */
export const mergeFetchedWithRecentLocal = (fetchedMessages = [], currentHistory = []) => {
  const fetched = Array.isArray(fetchedMessages) ? fetchedMessages : [];
  const current = Array.isArray(currentHistory) ? currentHistory : [];
  if (!current.length) return fetched;

  const now = Date.now();
  const RECENT_LOCAL_MS = 5 * 60 * 1000;
  const fetchedIds = new Set(fetched.map((m) => m?.message_id).filter(Boolean));
  const fetchedKeys = new Set(
    fetched.map((m) => `${String(m?.content || m?.text || "").trim()}|${String(m?.timestamp || "").slice(0, 19)}`)
  );

  const toKeep = current.filter((m) => {
    const isOperator = m?.role === "operator" || m?.is_user === false;
    if (!isOperator) return false;
    const ts = m?.timestamp ? new Date(m.timestamp).getTime() : 0;
    if (!ts || now - ts > RECENT_LOCAL_MS) return false;
    if (m?.message_id && fetchedIds.has(m.message_id)) return false;
    const key = `${String(m?.content || m?.text || "").trim()}|${String(m?.timestamp || "").slice(0, 19)}`;
    if (fetchedKeys.has(key)) return false;
    return true;
  });

  if (!toKeep.length) return fetched;
  return [...fetched, ...toKeep].sort(
    (a, b) => new Date(a?.timestamp || 0).getTime() - new Date(b?.timestamp || 0).getTime()
  );
};

/**
 * Attach SSE event listeners for live chat. Mutates `state` for reconnect/throttle flags.
 * @param {EventSource} eventSource
 * @param {Record<string, any>} ctx
 */
export const attachLiveChatSSEListeners = (eventSource, ctx) => {
  const {
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
    state,
  } = ctx;

  eventSource.onopen = () => {
    state.reconnectAttempt = 0;
    ctx.stopFallbackPolling?.();
    state.lastEventAt = Date.now();
    if (process.env.NODE_ENV === "development") {
      console.log("[SSE] connected");
    }
  };

  eventSource.addEventListener("conversations", async (event) => {
    if (!isMountedRef.current) return;
    try {
      const data = JSON.parse(event.data || "{}");
      state.lastEventAt = Date.now();
      const conversations = Array.isArray(data.conversations) ? data.conversations : null;
      const total = typeof data.total === "number" ? data.total : null;
      const hasMore =
        typeof data.has_more === "boolean"
          ? data.has_more
          : typeof data.hasMore === "boolean"
            ? data.hasMore
            : null;
      await refreshChats({
        preferredConversations: conversations,
        total,
        hasMore,
      });
      if (setIsLoading) setIsLoading(false);
    } catch (error) {
      console.error("SSE conversations parse error:", error);
      if (setIsLoading) setIsLoading(false);
    }
  });

  eventSource.addEventListener("new_message", async (event) => {
    if (!isMountedRef.current) return;
    if (state.handlingNewMessageEvent) return;
    state.handlingNewMessageEvent = true;
    try {
      const data = JSON.parse(event.data || "{}");
      state.lastEventAt = Date.now();
      const selected = selectedConversationRef.current;
      const convId = data?.conversation_id;
      const userId = data?.user_id;
      const message = data?.message;

      const msgId = message?.message_id;
      const isMatch =
        selected &&
        ((convId && selected.conversation?.conversation_id === convId) ||
          (userId && selected.conversation?.user_id === userId));
      if (isMatch && message && typeof message === "object" && message.timestamp) {
        setSelectedConversation((/** @type {SelectedConversation | null} */ prev) => {
          if (!prev || !prev.history) return prev;
          const content = String(message.content || message.text || "").trim();
          const exists = prev.history.some((/** @type {LiveChatMessage} */ m) => {
            if (msgId && m.message_id) return m.message_id === msgId;
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
          if (messageCacheRef?.current && prev.conversation) {
            const cacheKey = `${prev.conversation.user_id}_${prev.conversation.conversation_id}`;
            const existing = messageCacheRef.current.get(cacheKey);
            messageCacheRef.current.set(cacheKey, {
              messages: updatedHistory,
              hasMore: existing?.hasMore ?? (hasMoreMessagesRef?.current ?? false),
              cachedAt: Date.now(),
              isPartial: existing?.isPartial ?? false,
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

      if (updateChatListLocally && message && (convId || userId)) {
        updateChatListLocally(convId, userId, message);
      }

      if (messageCacheRef?.current && message && convId && userId) {
        const cacheKey = `${userId}_${convId}`;
        const existing = messageCacheRef.current.get(cacheKey);
        if (existing?.messages?.length) {
          const content = String(message.content || message.text || "").trim();
          const cacheMsgId = message?.message_id;
          const exists = existing.messages.some((/** @type {LiveChatMessage} */ m) => {
            if (cacheMsgId && m.message_id) return m.message_id === cacheMsgId;
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
              isPartial: existing.isPartial ?? false,
            });
            if (onOperatorMessageCached && (message.role === "operator" || message.is_user === false)) {
              onOperatorMessageCached(userId, convId, message);
            }
          }
        }
      }

      const now = Date.now();
      if (
        !debouncedSearchRef.current &&
        now - state.lastRefreshAt >= FULL_REFRESH_COOLDOWN_MS &&
        !state.debouncedRefreshScheduled
      ) {
        state.debouncedRefreshScheduled = true;
        setTimeout(async () => {
          if (!isMountedRef.current) return;
          state.debouncedRefreshScheduled = false;
          state.lastRefreshAt = Date.now();
          setIsRefreshing(true);
          try {
            await refreshChats();
          } finally {
            setIsRefreshing(false);
          }
        }, FULL_REFRESH_DELAY_MS);
      }

      if (!isMatch || !message) {
        await refreshSelectedConversationIfMatched(data);
      }
    } catch (error) {
      state.debouncedRefreshScheduled = false;
      setIsRefreshing(false);
      console.error("SSE new_message handler error:", error);
    } finally {
      state.handlingNewMessageEvent = false;
    }
  });

  eventSource.addEventListener("message_updated", (event) => {
    if (!isMountedRef.current) return;
    try {
      const data = JSON.parse(event.data || "{}");
      state.lastEventAt = Date.now();
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
            history: prev.history.map((/** @type {LiveChatMessage} */ m) =>
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
      state.lastEventAt = Date.now();
      const convId = data?.conversation_id;
      const userId = data?.user_id;
      const phone = data?.phone || "";
      const name = data?.name || "Unknown";
      if (convId && userId) {
        const now = new Date().toISOString();
        const previous = Array.isArray(activeConversationsRef.current)
          ? activeConversationsRef.current
          : [];
        const exists = previous.some(
          (/** @type {LiveChatConversation} */ c) => c.conversation_id === convId && c.user_id === userId
        );
        if (!exists) {
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
          const nextConversations = [newEntry, ...previous];
          setActiveConversations(nextConversations);
          activeConversationsRef.current = nextConversations;
        }
        setNewConversationIds((/** @type {Set<string>} */ prev) => new Set([...prev, convId]));
        setLastRefreshTime(new Date());
      }
    } catch (error) {
      console.error("SSE new_conversation handler error:", error);
    }
  });

  eventSource.addEventListener("heartbeat", () => {
    state.lastEventAt = Date.now();
  });
};
