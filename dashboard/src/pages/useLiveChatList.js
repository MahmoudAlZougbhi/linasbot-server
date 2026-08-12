/* eslint-disable no-unused-vars */
import { useCallback, useMemo } from "react";
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

export function useLiveChatList(s) {
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
    releaseConversation, sendOperatorMessage, updateOperatorStatus, submitFeedback, effectiveWaitingQueue, filteredWaitingQueue,
    withOperator, filteredWithOperator, botConversations, botConversationsForList, templateSendFilterLabel, templateSendFilterViewActive,
    getConversationLastTs, filteredBotConversations, formatConversationListDate, enrichWithRecency, liveBotConversations, historyBotConversations,
    mobileVisibleConversations, markConversationRead, mergeSelectedIntoWaitingQueue, applyWaitingQueue, applyTemplateSendFilter, clearTemplateSendFilter,
    fetchConversationMessages, getRecentOpFromSession, saveOperatorMessageToSession, mergeWithRecentOperatorMessages, buildPreviewHistory, getConversationUnreadCount,
    buildConversationFromQueueItem, selectConversation, openConversation, openWaitingConversation, appendMessageToSelectedConversation, updateChatListLocally,
    isRecording, recordedAudio, recordingTime, isSendingVoice, selectedImage, imageInputRef,
    startRecording, stopRecording, discardRecording, sendVoiceMessage, formatRecordingTime, handleImageSelect,
    discardImage, sendImageMessage, loadMoreChats, handleBotListScroll, handleManualRefresh, formatLastRefreshTime,
    loadMoreMessages, reloadSelectedConversationMessages, handleTakeOver, handleReleaseToBot, handleEndConversation, handleSendMessage,
    handleFeedback, getPreviousUserMessage, submitCorrection, submitLikeToFaq, handleFaqSaveChange, handleFaqSaveNew,
    submitEditMessage, selectedConversationId, selectedConversationUserId,
  } = s;

  const normalizeUserIdentity = useCallback(
    /**
     * @param {unknown} value
     * @returns {string}
     */
    (value) => String(value || "").trim().replace(/^\+/, ""),
    []
  );
  /** Format phone for display: +9613000000 → +961 3 000 000 */
  const formatPhoneForDisplay = useCallback(
    /**
     * @param {string | undefined} phone
     * @returns {string}
     */
    (phone) => {
    const s = String(phone || "").trim();
    if (!s || s === "Unknown") return s;
    const digits = s.replace(/\D/g, "");
    if (digits.startsWith("961") && digits.length >= 10) {
      const national = digits.slice(3);
      return `+961 ${national.slice(0, 1)} ${national.slice(1, 4)} ${national.slice(4)}`;
    }
    if (s.startsWith("+")) return s;
    return s;
    },
    []
  );
  const userRequestedReasons = useMemo(
    () => ["user_request", "customer_requested_human"],
    []
  );

  const normalizeConversationStatus = useCallback(
    /**
     * @param {string | undefined} status
     * @param {string | undefined} conversationState
     * @returns {string}
     */
    (status, conversationState) => {
    const raw = String(status || conversationState || "").toLowerCase();
    if (["human", "assigned_to_operator", "assigned"].includes(raw)) return "human";
    if (["waiting_human", "waiting_for_operator", "waiting", "pending"].includes(raw)) {
      return "waiting_human";
    }
    if (["closed", "resolved", "archived"].includes(raw)) return "closed";
    return "bot";
    },
    []
  );

  const normalizeIncomingConversation = useCallback(
    /**
     * @param {LiveChatConversation | null | undefined} conv
     * @returns {LiveChatConversation | null}
     */
    (conv) => {
    if (!conv || typeof conv !== "object") return null;
    const hta = conv.human_takeover_active;
    let postReleaseCooldownActive = false;
    const supUntil = conv.post_release_escalation_suppressed_until;
    if (supUntil) {
      const t = new Date(supUntil).getTime();
      if (!Number.isNaN(t) && t > Date.now()) {
        postReleaseCooldownActive = true;
      }
    }

    let normalizedStatus = normalizeConversationStatus(
      conv.status,
      conv.conversation_state
    );

    // Firestore/index can still have waiting_for_operator while human_takeover_active is false — trust release.
    if (hta === false || postReleaseCooldownActive) {
      if (normalizedStatus === "waiting_human") {
        normalizedStatus = "bot";
      }
      if (normalizedStatus === "human" && !conv.operator_id) {
        normalizedStatus = "bot";
      }
    }

    const lastActivity = conv.last_activity || conv.last_message_at || undefined;
    const rawLastMessage = conv.last_message;
    const previewText = conv.last_message_text ?? lastMessageContent(rawLastMessage) ?? "";
    /** @type {LiveChatMessage | null} */
    const normalizedLastMessage =
      rawLastMessage && typeof rawLastMessage === "object"
        ? rawLastMessage
        : previewText
          ? {
              content: previewText,
              timestamp: lastActivity,
              is_user: false,
            }
          : null;

    // Safety net: if backend status is temporarily stale but last bot message is a clear
    // handover/waiting phrase and no operator is assigned yet, surface it as waiting_human.
    // After "release to bot", last text can still be the waiting-queue line — do not re-classify as waiting.
    if (
      normalizedStatus === "bot" &&
      !conv.operator_id &&
      hta !== false &&
      !postReleaseCooldownActive
    ) {
      const lastText = String(
        (normalizedLastMessage && normalizedLastMessage.content) ||
          conv.last_message_text ||
          lastMessageContent(conv.last_message) ||
          ""
      ).toLowerCase();
      const waitingMarkers = [
        "تم تحويلك",
        "منكون معك",
        "you'll be transferred",
        "transferred to one of our staff",
        "we'll be with you shortly",
      ];
      if (waitingMarkers.some((marker) => lastText.includes(marker.toLowerCase()))) {
        normalizedStatus = "waiting_human";
      }
    }

    let outConversationState = conv.conversation_state;
    if ((hta === false || postReleaseCooldownActive) && normalizedStatus === "bot") {
      outConversationState = "bot_active";
    }

    return {
      ...conv,
      status: normalizedStatus,
      conversation_state: outConversationState,
      user_phone: conv.user_phone || conv.phone_number || "",
      last_activity: lastActivity,
      last_message: normalizedLastMessage,
    };
  }, [normalizeConversationStatus]);

  /**
   * @param {QueueItem[] | null | undefined} queue
   * @param {LiveChatConversation[] | null | undefined} activeList
   * @returns {QueueItem[]}
   */
  const mergeActiveWaitingIntoQueue = (queue, activeList) => {
    const activeWaiting = (activeList || []).filter((conv) => conv.status === "waiting_human");
    if (!activeWaiting.length) return queue ?? [];
    const queueKeys = new Set(
      (queue || []).map((item) => `${item.user_id}_${item.conversation_id}`)
    );
    /** @type {QueueItem[]} */
    const merged = [...(queue || [])];
    activeWaiting.forEach((conv) => {
      const key = `${conv.user_id}_${conv.conversation_id}`;
      if (queueKeys.has(key)) return;
      merged.push({
        conversation_id: conv.conversation_id,
        user_id: conv.user_id,
        user_name: conv.user_name,
        user_phone: conv.user_phone,
        wait_time_seconds: 0,
        message_count: conv.message_count || 0,
        last_message: lastMessageContent(conv.last_message) ?? "",
        reason: "user_request",
        sentiment: conv.sentiment || "neutral",
        language: conv.language || "ar",
        is_new_customer: conv.is_new_customer,
      });
    });
    return merged;
  };

  const mergeMissingActiveChats = useCallback(
    /**
     * @param {LiveChatConversation[]} incoming
     * @param {LiveChatConversation[] | null | undefined} existing
     * @returns {LiveChatConversation[]}
     */
    (incoming, existing) => {
    if (!Array.isArray(incoming)) return [];
    const existingList = existing || [];
    // Only preserve assigned-operator rows across pagination gaps. Stale waiting_human from a prior
    // render must not be re-injected when the conv drops off page 1 after release-to-bot (shows as "back on waiting").
    const keep = existingList.filter((conv) => conv.status === "human");
    if (!keep.length) return incoming;
    const incomingKeys = new Set(incoming.map((conv) => `${conv.user_id}_${conv.conversation_id}`));
    const missing = keep.filter((conv) => !incomingKeys.has(`${conv.user_id}_${conv.conversation_id}`));
    if (!missing.length) return incoming;
    return [...missing, ...incoming];
    },
    []
  );

  const applyServerConversations = useCallback(
    /**
     * @param {LiveChatConversation[] | unknown} incoming
     * @returns {void}
     */
    (incoming) => {
    if (!Array.isArray(incoming)) return;
    const normalizedIncoming = asConversationList(incoming)
      .map(normalizeIncomingConversation)
      .filter(isConversation);
    if (normalizedIncoming.length === 0) {
      if (activeConversationsRef.current?.length || cachedActiveConversationsRef.current?.length) {
        return;
      }
    }
    const baseline = activeConversationsRef.current?.length
      ? activeConversationsRef.current
      : cachedActiveConversationsRef.current;
    const merged = mergeMissingActiveChats(normalizedIncoming, baseline);
    setActiveConversations(merged);
    },
    [mergeMissingActiveChats, normalizeIncomingConversation]
  );


  Object.assign(s, {
    normalizeUserIdentity, formatPhoneForDisplay, userRequestedReasons, normalizeConversationStatus, normalizeIncomingConversation, mergeActiveWaitingIntoQueue,
    mergeMissingActiveChats, applyServerConversations,
  });
}
