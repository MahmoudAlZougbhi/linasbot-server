/* eslint-disable no-unused-vars */
import { useEffect } from "react";
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

export function useLiveChatEffects(s) {
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
    buildPreviewHistory, getConversationUnreadCount, buildConversationFromQueueItem, selectConversation, openConversation, openWaitingConversation,
    appendMessageToSelectedConversation, updateChatListLocally, isRecording, recordedAudio, recordingTime, isSendingVoice,
    selectedImage, imageInputRef, startRecording, stopRecording, discardRecording, sendVoiceMessage,
    formatRecordingTime, handleImageSelect, discardImage, sendImageMessage, loadMoreChats, handleBotListScroll,
    handleManualRefresh, formatLastRefreshTime, loadMoreMessages, reloadSelectedConversationMessages, handleTakeOver, handleReleaseToBot,
    handleEndConversation, handleSendMessage, handleFeedback, getPreviousUserMessage, submitCorrection, submitLikeToFaq,
    handleFaqSaveChange, handleFaqSaveNew, submitEditMessage, selectedConversationId, selectedConversationUserId,
  } = s;

  // Keep refs in sync with state
  useEffect(() => {
    selectedConversationRef.current = selectedConversation;
  }, [selectedConversation]);

  useEffect(() => {
    if (!isMobileView || selectedConversation?.conversation || !mobileDetailsOpen) return;
    setMobileDetailsOpen(false);
  }, [isMobileView, selectedConversation?.conversation, mobileDetailsOpen]);

  useEffect(() => {
    if (!isMobileView) return undefined;

    const handlePopState = () => {
      if (selectedConversationRef.current?.conversation) {
        setSelectedConversation(null);
        setMobileDetailsOpen(false);
      }
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [isMobileView]);

  useEffect(() => {
    hasMoreMessagesRef.current = hasMoreMessages;
  }, [hasMoreMessages]);

  useEffect(() => {
    activeConversationsRef.current = activeConversations;
    if (activeConversations?.length) {
      cachedActiveConversationsRef.current = activeConversations;
    }
  }, [activeConversations]);

  useEffect(() => {
    waitingQueueRef.current = waitingQueue;
    if (waitingQueue?.length) {
      cachedWaitingQueueRef.current = waitingQueue;
    }
  }, [waitingQueue]);

  useEffect(() => {
    try {
      sessionStorage.setItem(
        "liveChatActiveConversations",
        JSON.stringify(activeConversations || [])
      );
    } catch (err) {
      console.warn("LiveChat cache write error (active)", err);
    }
  }, [activeConversations]);

  useEffect(() => {
    try {
      sessionStorage.setItem(
        "liveChatWaitingQueue",
        JSON.stringify(waitingQueue || [])
      );
    } catch (err) {
      console.warn("LiveChat cache write error (waiting)", err);
    }
  }, [waitingQueue]);

  useEffect(() => {
    useMockDataRef.current = useMockData;
  }, [useMockData]);

  // Track mount state to avoid setState after unmount (fixes slowdown on repeated open/close)
  useEffect(() => {
    isMountedRef.current = true;
    const cachedChats = sessionStorage.getItem("liveChatActiveConversations");
    const cachedQueue = sessionStorage.getItem("liveChatWaitingQueue");
    if (cachedChats) {
      try {
        const parsed = asConversationList(JSON.parse(cachedChats));
        if (parsed.length > 0) {
          const normalized = parsed.map(normalizeIncomingConversation).filter(isConversation);
          setActiveConversations(normalized);
          activeConversationsRef.current = normalized;
          cachedActiveConversationsRef.current = normalized;
        }
      } catch (err) {
        console.warn("LiveChat cache parse error (active conversations)", err);
      }
    }
    if (cachedQueue) {
      try {
        const parsed = asQueueList(JSON.parse(cachedQueue));
        if (parsed.length > 0) {
          setWaitingQueue(parsed);
          waitingQueueRef.current = parsed;
          cachedWaitingQueueRef.current = parsed;
        }
      } catch (err) {
        console.warn("LiveChat cache parse error (waiting queue)", err);
      }
    }
    return () => {
      isMountedRef.current = false;
      try {
        sessionStorage.setItem("liveChatActiveConversations", JSON.stringify(activeConversationsRef.current || []));
        sessionStorage.setItem("liveChatWaitingQueue", JSON.stringify(waitingQueueRef.current || []));
      } catch (err) {
        console.warn("LiveChat cache write error", err);
      }
    };
  }, [normalizeIncomingConversation]);

  // Debounce search input (250ms) - WhatsApp-style snappy
  useEffect(() => {
    const timer = setTimeout(() => {
      const trimmed = liveSearchQuery.trim();
      setDebouncedSearch(trimmed);
      debouncedSearchRef.current = trimmed;
    }, 250);
    return () => clearTimeout(timer);
  }, [liveSearchQuery]);

  useEffect(() => {
    const query = (searchParams.get("search") || "").trim();
    setLiveSearchQuery((prev) => (prev === query ? prev : query));
  }, [searchParams]);

  Object.assign(s, {

  });
}
