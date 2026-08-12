/* eslint-disable no-unused-vars */
import { useCallback, useMemo } from "react";
import { markConversationRead as markConversationReadApi } from "../utils/liveChatApi";
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

export function useLiveChatFilters(s) {
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
    getLiveConversations, getWaitingQueue, getConversationMessages, takeoverConversation,
    releaseConversation, sendOperatorMessage, updateOperatorStatus, submitFeedback, normalizeUserIdentity, formatPhoneForDisplay,
    userRequestedReasons, normalizeConversationStatus, normalizeIncomingConversation, mergeActiveWaitingIntoQueue, mergeMissingActiveChats, applyServerConversations,
    applyTemplateSendFilter, clearTemplateSendFilter, fetchConversationMessages, getRecentOpFromSession, saveOperatorMessageToSession, mergeWithRecentOperatorMessages,
    buildPreviewHistory, getConversationUnreadCount, buildConversationFromQueueItem, selectConversation, openConversation, openWaitingConversation,
    appendMessageToSelectedConversation, updateChatListLocally, isRecording, recordedAudio, recordingTime, isSendingVoice,
    selectedImage, imageInputRef, startRecording, stopRecording, discardRecording, sendVoiceMessage,
    formatRecordingTime, handleImageSelect, discardImage, sendImageMessage, loadMoreChats, handleBotListScroll,
    handleManualRefresh, formatLastRefreshTime, loadMoreMessages, reloadSelectedConversationMessages, handleTakeOver, handleReleaseToBot,
    handleEndConversation, handleSendMessage, handleFeedback, getPreviousUserMessage, submitCorrection, submitLikeToFaq,
    handleFaqSaveChange, handleFaqSaveNew, submitEditMessage, selectedConversationId, selectedConversationUserId,
  } = s;

  const effectiveWaitingQueue = useMemo(
    () => mergeActiveWaitingIntoQueue(waitingQueue, activeConversations),
    [waitingQueue, activeConversations]
  );

  const filteredWaitingQueue = useMemo(() => {
    if (!waitingSearchTerm) return effectiveWaitingQueue;
    return effectiveWaitingQueue.filter((item) => {
      const name = (item.user_name || "").toLowerCase();
      const phone = (item.user_phone || "").toLowerCase();
      return name.includes(waitingSearchTerm) || phone.includes(waitingSearchTerm);
    });
  }, [effectiveWaitingQueue, waitingSearchTerm]);

  // Conversations where handover was done and we're talking with them (operator assigned)
  const withOperator = useMemo(
    () => {
      /**
       * @param {LiveChatConversation | null | undefined} conv
       * @returns {number}
       */
      const getLastTs = (conv) => {
        const lastMessage = conv?.last_message;
        const ts =
          conv?.last_activity ||
          (lastMessage && typeof lastMessage === "object" ? lastMessage.timestamp : undefined);
        return asTimestampMs(ts);
      };
      return activeConversations
        .filter((c) => {
          if (c.status !== "human") return false;
          // Some records can temporarily miss operator_id while still being assigned to a human.
          return true;
        })
        .sort((a, b) => getLastTs(b) - getLastTs(a));
    },
    [activeConversations]
  );

  const filteredWithOperator = useMemo(() => {
    if (!waitingSearchTerm) return withOperator;
    return withOperator.filter((conv) => {
      const name = (conv.user_name || "").toLowerCase();
      const phone = (conv.user_phone || "").toLowerCase();
      return name.includes(waitingSearchTerm) || phone.includes(waitingSearchTerm);
    });
  }, [withOperator, waitingSearchTerm]);
  // Only bot conversations (exclude waiting_human + with operator) - shown below, release to bot moves here
  const botConversations = useMemo(() => {
    const usersWithHumanOrWaiting = new Set(
      activeConversations
        .filter((c) => c.status === "human" || c.status === "waiting_human")
        .map((c) => normalizeUserIdentity(c.user_id))
        .filter(Boolean)
    );
    return activeConversations.filter((c) => {
      if (c.status !== "bot") return false;
      const normalizedUserId = normalizeUserIdentity(c.user_id);
      // Prevent "shadow" bot rows for users who already have an active human/waiting chat.
      return !usersWithHumanOrWaiting.has(normalizedUserId);
    });
  }, [activeConversations, normalizeUserIdentity]);

  const templateSendFilterViewActive =
    templateSendFilterActive && Boolean(templateSendFilterId);

  const botConversationsForList = useMemo(() => {
    if (!templateSendFilterViewActive) return botConversations;
    return (templateSendFilterChats || [])
      .map((c) => normalizeIncomingConversation(c))
      .filter(isConversation);
  }, [
    templateSendFilterViewActive,
    templateSendFilterChats,
    botConversations,
    normalizeIncomingConversation,
  ]);

  const templateSendFilterLabel = useMemo(() => {
    if (!templateSendFilterId) return "";
    const t = messagingTemplates[templateSendFilterId];
    return t?.name ? String(t.name) : templateSendFilterId;
  }, [templateSendFilterId, messagingTemplates]);

  const getConversationLastTs = useCallback(
    /**
     * @param {LiveChatConversation | null | undefined} conv
     * @returns {number}
     */
    (conv) => {
    const lastMessage = conv?.last_message;
    const ts =
      conv?.last_activity ||
      (lastMessage && typeof lastMessage === "object" ? lastMessage.timestamp : undefined);
    return asTimestampMs(ts);
    },
    []
  );

  const isBotDateFilterActive = Boolean(botDateFrom || botDateTo);

  const filteredBotConversations = useMemo(() => {
    if (templateSendFilterViewActive) {
      return botConversationsForList;
    }
    if (!isBotDateFilterActive) return botConversations;
    const start = botDateFrom ? new Date(`${botDateFrom}T00:00:00`) : null;
    const end = botDateTo ? new Date(`${botDateTo}T23:59:59.999`) : null;
    return botConversations.filter((conv) => {
      const lastTs = getConversationLastTs(conv);
      if (!lastTs) return false;
      if (start && lastTs < start.getTime()) return false;
      if (end && lastTs > end.getTime()) return false;
      return true;
    });
  }, [
    templateSendFilterViewActive,
    botConversationsForList,
    botConversations,
    botDateFrom,
    botDateTo,
    isBotDateFilterActive,
    getConversationLastTs,
  ]);

  const formatConversationListDate = useCallback(
    /**
     * @param {LiveChatConversation} conv
     * @returns {string}
     */
    (conv) => {
    const lastTs = getConversationLastTs(conv);
    if (!lastTs) return "No date";
    return new Date(lastTs).toLocaleDateString();
    },
    [getConversationLastTs]
  );

  const enrichWithRecency = useCallback(
    /**
     * @param {LiveChatConversation} conv
     * @returns {LiveChatListConversation}
     */
    (conv) => {
      const lastTs = getConversationLastTs(conv);
      const isRecent = lastTs > 0 && Date.now() - lastTs <= 15 * 60 * 1000;
      return { ...conv, _lastTs: lastTs, _isLive: Boolean(conv.is_live) || isRecent };
    },
    [getConversationLastTs]
  );

  const liveBotConversations = useMemo(
    () =>
      filteredBotConversations
        .map(enrichWithRecency)
        .filter((conv) => conv._isLive)
        .sort((a, b) => b._lastTs - a._lastTs),
    [filteredBotConversations, enrichWithRecency]
  );

  const historyBotConversations = useMemo(
    () =>
      filteredBotConversations
        .map(enrichWithRecency)
        .filter((conv) => !conv._isLive)
        .sort((a, b) => b._lastTs - a._lastTs),
    [filteredBotConversations, enrichWithRecency]
  );

  const mobileVisibleConversations = useMemo(() => {
    if (mobileListSection === "mine") return filteredWithOperator;
    if (mobileListSection === "bot") return [...liveBotConversations, ...historyBotConversations];
    return filteredWaitingQueue;
  }, [
    mobileListSection,
    filteredWithOperator,
    liveBotConversations,
    historyBotConversations,
    filteredWaitingQueue,
  ]);

  // Read count per waiting conversation for unread badge: key = `${user_id}_${conversation_id}`
  // Local state for optimistic UI; API unread_count is source of truth (persists across refresh)
  const markConversationRead = useCallback(
    /**
     * @param {string} userId
     * @param {string} conversationId
     * @param {number} messageCount
     * @returns {void}
     */
    (userId, conversationId, messageCount) => {
    const key = `${userId}_${conversationId}`;
    setReadMessageCountByConv((prev) => ({ ...prev, [key]: messageCount }));
    // Persist to backend so unread stays 0 after refresh/update
    markConversationReadApi({ userId, conversationId }).catch((/** @type {unknown} */ err) =>
      console.warn("[LiveChat] mark-read API failed:", errorMessage(err))
    );
    },
    []
  );
  const markWaitingConversationRead = markConversationRead;

  /**
   * Merge selected conversation into waiting queue when refetching so it doesn't disappear from the list
   * @param {QueueItem[] | null | undefined} newQueue
   * @param {import('react').MutableRefObject<SelectedConversation | null>} selectedRef
   * @returns {QueueItem[]}
   */
  const mergeSelectedIntoWaitingQueue = (newQueue, selectedRef) => {
    const selected = selectedRef?.current;
    if (!selected?.conversation || selected.conversation.status !== "waiting_human") return newQueue ?? [];
    const c = selected.conversation;
    const inQueue = (newQueue ?? []).some((q) => q.conversation_id === c.conversation_id && q.user_id === c.user_id);
    if (inQueue) return newQueue ?? [];
    /** @type {QueueItem} */
    const synthetic = {
      conversation_id: c.conversation_id,
      user_id: c.user_id,
      user_name: c.user_name,
      user_phone: c.user_phone,
      wait_time_seconds: 0,
      message_count: c.message_count || 0,
      unread_count: c.unread_count,
      last_message: lastMessageContent(c.last_message) ?? "",
      reason: "user_request",
      sentiment: c.sentiment || "neutral",
    };
    return [synthetic, ...(newQueue ?? [])];
  };

  /**
   * @param {{ success?: boolean; queue?: QueueItem[] } | null | undefined} queueResponse
   * @returns {void}
   */
  const applyWaitingQueue = (queueResponse) => {
    const incoming = queueResponse?.queue;
    if (!Array.isArray(incoming)) return;
    // Always apply valid queue response - including empty. Previously we skipped empty
    // when we had cached items, which caused taken-over conversations to stay in
    // Waiting after refresh (API correctly returns empty/smaller queue, but we kept stale state).
    setWaitingQueue(mergeSelectedIntoWaitingQueue(incoming, selectedConversationRef));
  };

  Object.assign(s, {
    effectiveWaitingQueue, filteredWaitingQueue, withOperator, filteredWithOperator, botConversations, botConversationsForList,
    templateSendFilterLabel, templateSendFilterViewActive, isBotDateFilterActive, getConversationLastTs, filteredBotConversations, formatConversationListDate, enrichWithRecency,
    liveBotConversations, historyBotConversations, mobileVisibleConversations, markConversationRead, markWaitingConversationRead, mergeSelectedIntoWaitingQueue, applyWaitingQueue,
  });
}
