/* eslint-disable no-unused-vars */
import { useCallback, useEffect } from "react";
import { useLiveChatMediaComposer } from "../hooks/useLiveChatMediaComposer";
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

export function useLiveChatSelection(s) {
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
    effectiveWaitingQueue, filteredWaitingQueue, withOperator, filteredWithOperator, botConversations, botConversationsForList,
    templateSendFilterLabel, templateSendFilterViewActive, getConversationLastTs, filteredBotConversations, formatConversationListDate, enrichWithRecency,
    liveBotConversations, historyBotConversations, mobileVisibleConversations, markConversationRead, mergeSelectedIntoWaitingQueue, applyWaitingQueue,
    applyTemplateSendFilter, clearTemplateSendFilter, fetchConversationMessages, getRecentOpFromSession, saveOperatorMessageToSession, mergeWithRecentOperatorMessages,
    buildPreviewHistory, getConversationUnreadCount, buildConversationFromQueueItem, loadMoreChats, handleBotListScroll, handleManualRefresh,
    formatLastRefreshTime, loadMoreMessages, reloadSelectedConversationMessages, handleTakeOver, handleReleaseToBot, handleEndConversation,
    handleSendMessage, handleFeedback, getPreviousUserMessage, submitCorrection, submitLikeToFaq, handleFaqSaveChange,
    handleFaqSaveNew, submitEditMessage, selectedConversationId, selectedConversationUserId, markWaitingConversationRead,
  } = s;

  const selectConversation = useCallback(
    /**
     * @param {LiveChatConversation} conv
     * @returns {void}
     */
    (conv) => {
    const cacheKey = `${conv.user_id}_${conv.conversation_id}`;
    const cached = messageCacheRef.current.get(cacheKey);
    const cachedMessages = cached?.messages ?? [];
    const hasCachedMessages = cachedMessages.length > 0;
    const knownCount = Math.max(conv?.message_count || 0, cachedMessages.length);
    markConversationRead(conv.user_id, conv.conversation_id, knownCount);
    setSelectedConversation({
      conversation: conv,
      history: hasCachedMessages ? cachedMessages : [],
    });
    if (hasCachedMessages) {
      setHasMoreMessages(cached?.hasMore ?? !cached?.isPartial);
      setMessagesLoading(false);
    } else {
      // No cached history: show loader, then render full fetched history in one pass.
      setHasMoreMessages(false);
      setMessagesLoading(true);
    }
    },
    [markConversationRead]
  );

  const openConversation = useCallback(
    /**
     * @param {LiveChatConversation} conv
     * @returns {void}
     */
    (conv) => {
    if (isMobileView && !selectedConversationRef.current?.conversation) {
      window.history.pushState({ mobileLiveChatOpen: true }, "");
    }
    setMobileDetailsOpen(false);
    selectConversation(conv);
    },
    [isMobileView, selectConversation]
  );

  const openWaitingConversation = useCallback(
    /**
     * @param {QueueItem} item
     * @returns {void}
     */
    (item) => {
    markWaitingConversationRead(item.user_id, item.conversation_id, item.message_count || 0);
    openConversation(buildConversationFromQueueItem(item));
    },
    [buildConversationFromQueueItem, markWaitingConversationRead, openConversation]
  );

  useEffect(() => {
    if (!selectedConversation?.conversation) return;
    const c = selectedConversation.conversation;
    const count = Math.max(c.message_count || 0, selectedConversation.history?.length || 0);
    markConversationRead(c.user_id, c.conversation_id, count);
  }, [
    selectedConversation?.conversation,
    selectedConversation?.conversation?.conversation_id,
    selectedConversation?.history?.length,
    markConversationRead,
  ]);

  /**
   * @param {LiveChatMessage} newMessage
   * @returns {void}
   */
  const appendMessageToSelectedConversation = (newMessage) => {
    setSelectedConversation((previous) => {
      if (!previous) return previous;
      /** @type {SelectedConversation} */
      const updated = {
        ...previous,
        history: [...(previous.history || []), newMessage],
      };
      if (previous.conversation) {
        const cacheKey = `${previous.conversation.user_id}_${previous.conversation.conversation_id}`;
        messageCacheRef.current.set(cacheKey, {
          messages: updated.history,
          hasMore: hasMoreMessages,
          cachedAt: Date.now(),
          isPartial: false,
        });
      }
      return updated;
    });
  };

  /**
   * Update chat list locally (move to top + update last_message) without calling /unified-chats
   * @param {string | undefined} conversationId
   * @param {string | undefined} userId
   * @param {LiveChatMessage} message
   * @returns {void}
   */
  const updateChatListLocally = (conversationId, userId, message) => {
    setActiveConversations((prev) => {
      let idx = -1;
      if (conversationId) {
        idx = prev.findIndex((c) => c.conversation_id === conversationId);
      } else if (userId) {
        // Fallback only when conversation ID is unavailable.
        idx = prev.findIndex((c) => c.user_id === userId);
      }
      const conv = idx >= 0 ? prev[idx] : undefined;
      if (!conv) return prev;
      const ts = message?.timestamp || new Date().toISOString();
      /** @type {LiveChatConversation} */
      const updated = {
        ...conv,
        last_message: {
          content: message?.content ?? message?.text ?? "",
          is_user: message?.is_user ?? message?.role === "user",
          timestamp: ts,
        },
        last_activity: ts,
      };
      const rest = prev.filter((_, i) => i !== idx);
      return [updated, ...rest];
    });
  };

  const {
    isRecording,
    recordedAudio,
    recordingTime,
    isSendingVoice,
    selectedImage,
    imageInputRef,
    startRecording,
    stopRecording,
    discardRecording,
    sendVoiceMessage,
    formatRecordingTime,
    handleImageSelect,
    discardImage,
    sendImageMessage,
  } = useLiveChatMediaComposer({
    selectedConversation,
    sendOperatorMessage,
    onAppendMessage: appendMessageToSelectedConversation,
  });

  Object.assign(s, {
    selectConversation, openConversation, openWaitingConversation, appendMessageToSelectedConversation, updateChatListLocally, isRecording,
    recordedAudio, recordingTime, isSendingVoice, selectedImage, imageInputRef, startRecording,
    stopRecording, discardRecording, sendVoiceMessage, formatRecordingTime, handleImageSelect, discardImage,
    sendImageMessage,
  });
}
