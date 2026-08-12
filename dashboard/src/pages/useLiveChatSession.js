/* eslint-disable no-unused-vars */
import { useCallback, useEffect } from "react";
import toast from "react-hot-toast";
import { errorMessage } from "../utils/apiValidate";
import {
  CHAT_LIST_PAGE_SIZE,
  MESSAGE_CACHE_TTL_MS,
  asConversationList,
  asQueueList,
  asMessageList,
  asText,
  asTimestampMs,
  isConversation,
  messageBody,
  isGatewayTimeout,
  lastMessageContent,
  isSocialChannelUser,
} from "./LiveChat.helpers";

export function useLiveChatSession(s) {
  const {
    isMobileView, searchParams, authUser, operatorId, operatorStatus, waitingSearchTerm,
    activeConversations, setActiveConversations, selectedConversation, setSelectedConversation, waitingQueue, setWaitingQueue,
    messageInput, setMessageInput, isLoading, setIsLoading, useMockData, setUseMockData,
    feedbackModal, setFeedbackModal, editMessageModal, setEditMessageModal, faqCorrectionModal, setFaqCorrectionModal,
    lastRefreshTime, setLastRefreshTime, newConversationIds, setNewConversationIds, isRefreshing, setIsRefreshing,
    isSending, setIsSending, messagesLoading, setMessagesLoading, loadingMoreMessages, setLoadingMoreMessages,
    hasMoreMessages, setHasMoreMessages, liveSearchQuery, setLiveSearchQuery, debouncedSearch, setDebouncedSearch,
    botDateFrom, setBotDateFrom, botDateTo, setBotDateTo, templateSendFilterId, setTemplateSendFilterId,
    templateSendFilterActive, setTemplateSendFilterActive, templateSendFilterChats, setTemplateSendFilterChats, templateSendFilterMeta, setTemplateSendFilterMeta,
    templateSendFilterLoading, setTemplateSendFilterLoading, messagingTemplates, setMessagingTemplates, setChatPage, nextCursor,
    setNextCursor, hasMoreChats, setHasMoreChats, loadingMoreChats, setLoadingMoreChats, rebuildingIndex,
    setRebuildingIndex, sidebarCollapsed, setSidebarCollapsed, botPanelOpen, setBotPanelOpen, mobileListSection,
    setMobileListSection, mobileDetailsOpen, setMobileDetailsOpen, mobileFilterSheetOpen, setMobileFilterSheetOpen, readMessageCountByConv,
    setReadMessageCountByConv, isReleasing, setIsReleasing, releasingRef, sendingRef, editContent,
    setEditContent, isSubmittingEdit, setIsSubmittingEdit, faqContext, setFaqContext, faqEditAnswer,
    setFaqEditAnswer, faqContextLoading, setFaqContextLoading, faqSubmitting, setFaqSubmitting, messagesContainerRef,
    messagesEndRef, selectedConversationRef, activeConversationsRef, waitingQueueRef, cachedActiveConversationsRef, cachedWaitingQueueRef,
    useMockDataRef, debouncedSearchRef, isMountedRef, previousConversationIdRef, previousMessageCountRef, forceBottomOnOpenRef,
    messageCacheRef, hasMoreMessagesRef, autoLoadedPagesRef, botListRef, botLoadMoreSentinelRef, botListScrollThrottleRef,
    botFloatingScrollRef, loadMoreInProgressRef, loadMoreCooldownUntilRef, messagesLoadingStartRef, getUnifiedChats, getChatsByTemplateSendLog,
    getLiveConversations, getWaitingQueue, rebuildLiveChatIndex, simulateWebhook, getConversationMessages, takeoverConversation,
    releaseConversation, sendOperatorMessage, updateOperatorStatus, submitFeedback, normalizeUserIdentity, formatPhoneForDisplay,
    userRequestedReasons, normalizeConversationStatus, normalizeIncomingConversation, mergeActiveWaitingIntoQueue, mergeMissingActiveChats, applyServerConversations,
    effectiveWaitingQueue, filteredWaitingQueue, withOperator, filteredWithOperator, botConversations, botConversationsForList,
    templateSendFilterLabel, templateSendFilterViewActive, getConversationLastTs, filteredBotConversations, formatConversationListDate, enrichWithRecency,
    liveBotConversations, historyBotConversations, mobileVisibleConversations, markConversationRead, mergeSelectedIntoWaitingQueue, applyWaitingQueue,
    selectConversation, openConversation, openWaitingConversation, appendMessageToSelectedConversation, updateChatListLocally, isRecording,
    recordedAudio, recordingTime, isSendingVoice, selectedImage, imageInputRef, startRecording,
    stopRecording, discardRecording, sendVoiceMessage, formatRecordingTime, handleImageSelect, discardImage,
    sendImageMessage, loadMoreChats, handleBotListScroll, handleManualRefresh, formatLastRefreshTime, loadMoreMessages,
    reloadSelectedConversationMessages, handleTakeOver, handleReleaseToBot, handleEndConversation, handleSendMessage, handleFeedback,
    getPreviousUserMessage, submitCorrection, submitLikeToFaq, handleFaqSaveChange, handleFaqSaveNew, submitEditMessage,
    selectedConversationId, selectedConversationUserId,
  } = s;

  // Smart Messaging HTTP API is product-disabled (403); do not fetch templates.
  const applyTemplateSendFilter = useCallback(async () => {
    if (!templateSendFilterId) {
      toast.error("Choose a template");
      return;
    }
    setTemplateSendFilterLoading(true);
    try {
      const r = await getChatsByTemplateSendLog(
        templateSendFilterId,
        botDateFrom,
        botDateTo
      );
      if (!r?.success) {
        toast.error(r?.error || "Filter failed");
        return;
      }
      setTemplateSendFilterChats(asConversationList(r.chats));
      setTemplateSendFilterMeta({
        log_entries_matched: r.log_entries_matched,
        distinct_recipients: r.distinct_recipients,
        matched_chats: r.matched_chats,
        index_scanned: r.index_scanned,
      });
      setTemplateSendFilterActive(true);
      setHasMoreChats(false);
      setNextCursor(null);
      const n = r.matched_chats ?? 0;
      toast.success(
        n > 0
          ? `${n} conversation(s) matched (send log + chat index)`
          : "No conversations matched in the index scan — try wider dates or Rebuild index"
      );
    } catch (e) {
      toast.error(errorMessage(e) || "Filter failed");
    } finally {
      setTemplateSendFilterLoading(false);
    }
  }, [
    templateSendFilterId,
    botDateFrom,
    botDateTo,
    getChatsByTemplateSendLog,
  ]);

  const clearTemplateSendFilter = useCallback(() => {
    setTemplateSendFilterActive(false);
    setTemplateSendFilterChats([]);
    setTemplateSendFilterMeta(null);
    setTemplateSendFilterId("");
  }, []);

  useEffect(() => {
    updateOperatorStatus(operatorId, operatorStatus).catch(() => {
      // Keep UI responsive even if status update endpoint is temporarily unavailable.
    });
  }, [operatorStatus, operatorId, updateOperatorStatus]);

  // Fetch conversation messages: use same axios as list (getUnifiedChats) so request hits same origin
  const fetchConversationMessages = useCallback(
    /**
     * @param {string} userId
     * @param {string} conversationId
     * @param {number} [days]
     * @param {string | null} [before]
     * @param {number} [day_window]
     * @param {number} [limit]
     * @returns {Promise<{ messages: LiveChatMessage[]; hasMore: boolean }>}
     */
    async (userId, conversationId, days = 0, before = null, day_window = 0, limit = 50) => {
      const result = await getConversationMessages(
        userId,
        conversationId,
        days,
        before,
        day_window,
        limit
      );
      return {
        messages: asMessageList(result?.messages),
        hasMore: Boolean(result?.hasMore),
      };
    },
    [getConversationMessages]
  );

  const SESSION_RECENT_OP_KEY = "live_chat_recent_op";
  const RECENT_OP_TTL_MS = 120000;

  const getRecentOpFromSession = useCallback(
    /**
     * @param {string} cacheKey
     * @returns {LiveChatMessage[]}
     */
    (cacheKey) => {
    try {
      const raw = sessionStorage.getItem(SESSION_RECENT_OP_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      /** @type {RecentOperatorSessionEntry[]} */
      const arr = Array.isArray(parsed) ? parsed : [];
      const now = Date.now();
      const parts = (cacheKey || "").split("_");
      const head = parts[0] ?? "";
      const altKey = parts.length >= 2
        ? `${head.startsWith("+") ? head.slice(1) : `+${head}`}_${parts.slice(1).join("_")}`
        : "";
      return arr.filter((e) => {
        if (!e?.cacheKey || now - (e.ts || 0) > RECENT_OP_TTL_MS) return false;
        return e.cacheKey === cacheKey || e.cacheKey === altKey || e.altKey === cacheKey;
      }).flatMap((e) => e.messages || []);
    } catch {
      return [];
    }
    },
    []
  );

  const saveOperatorMessageToSession = useCallback(
    /**
     * @param {string} userId
     * @param {string} convId
     * @param {LiveChatMessage} message
     * @returns {void}
     */
    (userId, convId, message) => {
    if (!userId || !convId || !message) return;
    const isOp = message.role === "operator" || message.is_user === false;
    if (!isOp) return;
    try {
      const cacheKey = `${userId}_${convId}`;
      const raw = sessionStorage.getItem(SESSION_RECENT_OP_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      /** @type {RecentOperatorSessionEntry[]} */
      const arr = (Array.isArray(parsed) ? parsed : []).filter(
        (/** @type {RecentOperatorSessionEntry} */ e) => e?.ts && Date.now() - e.ts < RECENT_OP_TTL_MS
      );
      const entry = arr.find((e) => e.cacheKey === cacheKey);
      /** @type {LiveChatMessage} */
      const msg = { ...message, role: "operator", is_user: false };
      if (entry) {
        const exists = (entry.messages || []).some(
          (m) => messageBody(m).trim() === messageBody(msg).trim()
        );
        if (!exists) entry.messages = [...(entry.messages || []), msg];
      } else {
        arr.push({ cacheKey, ts: Date.now(), messages: [msg] });
      }
      sessionStorage.setItem(SESSION_RECENT_OP_KEY, JSON.stringify(arr.slice(-20)));
    } catch {
      // sessionStorage may be unavailable
    }
    },
    []
  );

  // Merge API messages with recently sent operator messages from cache + sessionStorage (prevents disappearing on refresh)
  const mergeWithRecentOperatorMessages = useCallback(
    /**
     * @param {LiveChatMessage[]} apiMessages
     * @param {string} cacheKey
     * @returns {LiveChatMessage[]}
     */
    (apiMessages, cacheKey) => {
    const cache = messageCacheRef.current;
    let cached = cache?.get(cacheKey)?.messages || [];
    if (!cached.length && cacheKey) {
      const parts = cacheKey.split("_");
      if (parts.length >= 2) {
        const userId = parts[0] ?? "";
        const rest = parts.slice(1).join("_");
        const altUserId = userId.startsWith("+") ? userId.slice(1) : `+${userId}`;
        const altKey = `${altUserId}_${rest}`;
        cached = cache?.get(altKey)?.messages || cached;
      }
    }
    if (!cached.length && cacheKey) {
      cached = getRecentOpFromSession(cacheKey);
    }
    const api = apiMessages || [];
    const now = Date.now();
    const RECENT_MS = 120000;
    const recentOperator = cached.filter((m) => {
      const isOp = m.is_user === false || m.role === "operator";
      const ts = asTimestampMs(m.timestamp);
      return isOp && now - ts < RECENT_MS;
    });
    const apiKeys = new Set(
      api.map((m) => `${messageBody(m).trim()}|${asText(m.timestamp).slice(0, 19)}`)
    );
    const toAdd = recentOperator.filter((m) => {
      const key = `${messageBody(m).trim()}|${asText(m.timestamp).slice(0, 19)}`;
      if (apiKeys.has(key)) return false;
      const mTs = asTimestampMs(m.timestamp);
      const inApi = api.some(
        (a) =>
          messageBody(a).trim() === messageBody(m).trim() &&
          Math.abs(asTimestampMs(a.timestamp) - mTs) < 60000
      );
      return !inApi;
    });
    if (toAdd.length === 0) return api;
    const combined = [...api, ...toAdd].sort(
      (a, b) => asTimestampMs(a?.timestamp) - asTimestampMs(b?.timestamp)
    );
    return combined;
    },
    [getRecentOpFromSession]
  );

  const buildPreviewHistory = useCallback(
    /**
     * @param {LiveChatConversation | null | undefined} conversation
     * @returns {LiveChatMessage[]}
     */
    (conversation) => {
    const preview = conversation?.last_message;
    if (!preview || typeof preview !== "object") return [];
    const text = String(preview.content ?? preview.text ?? "").trim();
    if (!text) return [];
    const timestamp =
      preview.timestamp ||
      conversation?.last_activity ||
      conversation?.last_message_at ||
      new Date().toISOString();
    return [
      {
        message_id: `preview_${conversation?.conversation_id || "chat"}_${timestamp}`,
        timestamp,
        is_user: Boolean(preview.is_user),
        content: text,
        text,
        type: "text",
        role: preview.is_user ? "user" : "assistant",
        handled_by: preview.is_user ? "human" : "ai",
      },
    ];
    },
    []
  );

  const getConversationUnreadCount = useCallback(
    /**
     * @param {QueueItem | LiveChatConversation | null | undefined} conversation
     * @returns {number}
     */
    (conversation) => {
    if (!conversation) return 0;
    const readKey = `${conversation.user_id}_${conversation.conversation_id}`;
    const readCount = readMessageCountByConv[readKey] ?? 0;
    const msgCount = conversation.message_count || 0;
    if (readCount > 0 && readCount >= msgCount) return 0;
    if (typeof conversation.unread_count === "number") return conversation.unread_count;
    return Math.max(0, msgCount - readCount);
    },
    [readMessageCountByConv]
  );

  const buildConversationFromQueueItem = useCallback(
    /**
     * @param {QueueItem} item
     * @returns {LiveChatConversation}
     */
    (item) => {
    return activeConversations.find(
      (c) =>
        c.conversation_id === item.conversation_id &&
        c.user_id === item.user_id
    ) || {
      conversation_id: item.conversation_id,
      user_id: item.user_id,
      user_name: item.user_name,
      user_phone: item.user_phone,
      status: "waiting_human",
      language: item.language || "ar",
      sentiment: item.sentiment,
      message_count: item.message_count || 0,
      last_message: item.last_message ? { content: lastMessageContent(item.last_message) } : null,
      is_new_customer: item.is_new_customer,
      wait_time_seconds: item.wait_time_seconds,
      reason: item.reason,
      unread_count: item.unread_count,
    };
    },
    [activeConversations]
  );

  Object.assign(s, {
    applyTemplateSendFilter, clearTemplateSendFilter, fetchConversationMessages, getRecentOpFromSession, saveOperatorMessageToSession, mergeWithRecentOperatorMessages,
    buildPreviewHistory, getConversationUnreadCount, buildConversationFromQueueItem,
  });
}
