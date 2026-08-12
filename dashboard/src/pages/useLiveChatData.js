/* eslint-disable no-unused-vars */
import { useEffect } from "react";
import toast from "react-hot-toast";
import { useLiveChatSSE } from "../hooks/useLiveChatSSE";
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

export function useLiveChatData(s) {
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
    handleFaqSaveChange, handleFaqSaveNew, submitEditMessage,
  } = s;

  // Fetch real data: on initial load (no search) rely on SSE only - no duplicate /unified-chats call
  useEffect(() => {
    const fetchLiveData = async () => {
      if (!isMountedRef.current) return;
      if (!activeConversations.length) {
        if (isMountedRef.current) setIsLoading(true);
      }

      // Initial load with no search: keep chats visible even if one endpoint fails.
      if (!debouncedSearch.trim()) {
        try {
          const [chatsResult, queueResult] = await Promise.allSettled([
            getUnifiedChats("", 1, CHAT_LIST_PAGE_SIZE),
            getWaitingQueue(),
          ]);
          if (!isMountedRef.current) return;

          let chatsResponse =
            chatsResult.status === "fulfilled" ? chatsResult.value : null;

          if (!chatsResponse?.success) {
            try {
              const fallback = await getLiveConversations("");
              if (fallback?.success && Array.isArray(fallback.conversations)) {
                chatsResponse = {
                  success: true,
                  chats: fallback.conversations,
                  has_more: false,
                };
              }
            } catch (fallbackErr) {
              console.warn("Live Chat initial fallback fetch error:", fallbackErr);
            }
          }

          if (chatsResponse?.success && Array.isArray(chatsResponse.chats)) {
            applyServerConversations(chatsResponse.chats);
            setHasMoreChats(chatsResponse.has_more ?? false);
            setNextCursor(chatsResponse.next_cursor ?? null);
            setChatPage(1);
            setUseMockData(false);
            autoLoadedPagesRef.current = 1;
          } else if (!activeConversationsRef.current?.length) {
            /* mock fallback removed — show empty/error honestly */ setUseMockData(false);
          }

          if (queueResult.status === "fulfilled" && queueResult.value?.success && queueResult.value?.queue) {
            applyWaitingQueue(queueResult.value);
          }
        } catch (err) {
          if (!isMountedRef.current) return;
          console.warn("Live Chat initial fetch error:", err);
        } finally {
          if (isMountedRef.current) setIsLoading(false);
        }
        return;
      }

      try {
        let chatsResponse;
        try {
          chatsResponse = await getUnifiedChats(debouncedSearch, 1, CHAT_LIST_PAGE_SIZE);
          if (!isMountedRef.current) return;
        } catch (err) {
          if (isGatewayTimeout(err)) {
            try {
              const fallback = await getLiveConversations(debouncedSearch);
              chatsResponse = fallback.success && fallback.conversations
                ? { success: true, chats: fallback.conversations, has_more: false }
                : { success: false, chats: [] };
              if (chatsResponse.success) {
                toast("Showing live chats only (server busy)", { icon: "⚡" });
              } else {
                throw new Error("Fallback failed");
              }
            } catch {
              toast.error("Server is busy. Data will refresh when available.");
              return;
            }
          } else {
            throw err;
          }
        }
        if (chatsResponse?.success && isMountedRef.current) {
          const chats = asConversationList(chatsResponse.chats ?? chatsResponse.conversations);
          applyServerConversations(chats);
          setChatPage(1);
          setNextCursor(chatsResponse.next_cursor ?? null);
          setHasMoreChats(chatsResponse.has_more || false);
          setUseMockData(false);
          autoLoadedPagesRef.current = 1;

          const currentSelection = selectedConversationRef.current;
          if (currentSelection) {
            const updatedConv = chats.find(
              (c) => c.conversation_id === currentSelection.conversation.conversation_id
            );
            if (updatedConv && isMountedRef.current) {
              setSelectedConversation((prev) => (prev ? { ...prev, conversation: updatedConv } : prev));
            }
          }
        } else if (isMountedRef.current && !activeConversations.length) {
          /* mock fallback removed — show empty/error honestly */ setUseMockData(false);
        }

        if (!debouncedSearch.trim()) {
          getWaitingQueue()
            .then((queueResponse) => {
              if (!isMountedRef.current) return;
              if (queueResponse?.success) {
                applyWaitingQueue(queueResponse);
              }
            })
            .catch(() => {});
        }
      } catch (error) {
        if (!isMountedRef.current) return;
        console.error("Error fetching live chat data:", error);
        if (isGatewayTimeout(error)) {
          toast.error("Server is busy. Will retry automatically.");
        } else if (!activeConversations.length) {
          /* mock fallback removed — show empty/error honestly */ setUseMockData(false);
        }
      } finally {
        if (isMountedRef.current) setIsLoading(false);
      }
    };

    fetchLiveData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, applyServerConversations]);

  useLiveChatSSE({
    enabled: !useMockData,
    isMountedRef,
    useMockDataRef,
    activeConversationsRef,
    selectedConversationRef,
    debouncedSearchRef,
    getUnifiedChats,
    getWaitingQueue,
    applyWaitingQueue,
    chatListPageSize: CHAT_LIST_PAGE_SIZE,
    fetchConversationMessages,
    setActiveConversations: applyServerConversations,
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
    onOperatorMessageCached: saveOperatorMessageToSession,
  });

  // Fallback: if SSE doesn't populate, fetch once manually (single safety net)
  useEffect(() => {
    if (debouncedSearch.trim() || useMockData) return;
    const t = setTimeout(async () => {
      if (!isMountedRef.current) return;
      if (activeConversationsRef.current.length > 0) return;
      setIsLoading(true);
      try {
        let r = await getUnifiedChats("", 1, CHAT_LIST_PAGE_SIZE);
        if (!r?.success || asConversationList(r?.chats).length === 0) {
          const fallback = await getLiveConversations("");
          if (fallback?.success && Array.isArray(fallback.conversations) && fallback.conversations.length > 0) {
            r = { success: true, chats: fallback.conversations, has_more: false };
          }
        }
        if (!isMountedRef.current) return;
        if (r?.success && asConversationList(r?.chats).length > 0) {
          applyServerConversations(r.chats);
          setNextCursor(r.next_cursor ?? null);
          setHasMoreChats(r.has_more ?? false);
          setChatPage(1);
          autoLoadedPagesRef.current = 1;
        }
      } catch (e) {
        console.warn("Live Chat fallback fetch failed:", e);
      } finally {
        if (isMountedRef.current) setIsLoading(false);
      }
    }, 15000);
    return () => clearTimeout(t);
  }, [debouncedSearch, useMockData, getUnifiedChats, getLiveConversations, applyServerConversations, setIsLoading, setHasMoreChats, setChatPage]);

  const selectedConversationId = selectedConversation?.conversation?.conversation_id;
  const selectedConversationUserId = selectedConversation?.conversation?.user_id;

  useEffect(() => {
    if (selectedConversationId) {
      // Force initial open at bottom even if messages hydrate in multiple steps.
      forceBottomOnOpenRef.current = selectedConversationId;
    } else {
      forceBottomOnOpenRef.current = null;
    }
  }, [selectedConversationId]);

  // ✅ Fetch messages when selected conversation changes (not polling)
  useEffect(() => {
    if (!selectedConversationId || !selectedConversationUserId || useMockData) {
      setMessagesLoading(false);
      return;
    }

    let cancelled = false;
    const loadingFallbackTimer = setTimeout(() => {
      if (!isMountedRef.current) return;
      if (cancelled) return;
      if (
        selectedConversationRef.current?.conversation?.conversation_id ===
        selectedConversationId
      ) {
        setMessagesLoading(false);
      }
    }, 12000);
    const cacheKey = `${selectedConversationUserId}_${selectedConversationId}`;
    const cached = messageCacheRef.current.get(cacheKey);
    const cachedMessages = cached?.messages ?? [];
    const cacheAge = cached?.cachedAt ? Date.now() - cached.cachedAt : Infinity;
    const cacheFresh = cached && !cached.isPartial && cacheAge < MESSAGE_CACHE_TTL_MS;

    if (cachedMessages.length) {
      setSelectedConversation((prev) => {
        if (!prev || prev.conversation?.conversation_id !== selectedConversationId) return prev;
        return { ...prev, history: cachedMessages };
      });
      setHasMoreMessages(Boolean(cached?.hasMore));
    }

    if (cacheFresh) {
      setMessagesLoading(false);
      return () => {
        cancelled = true;
      };
    }

    const fetchMessages = async () => {
      setMessagesLoading(cachedMessages.length === 0);
      try {
        const { messages, hasMore } = await fetchConversationMessages(
          selectedConversationUserId,
          selectedConversationId,
          0,
          null,
          0,
          100
        );
        if (!isMountedRef.current || cancelled) return;

        const merged = mergeWithRecentOperatorMessages(messages || [], cacheKey);

        messageCacheRef.current.set(cacheKey, {
          messages: merged,
          hasMore: hasMore || false,
          cachedAt: Date.now(),
          isPartial: false,
        });

        setSelectedConversation((prev) => {
          if (!prev || prev.conversation?.conversation_id !== selectedConversationId) {
            return prev;
          }
          return { ...prev, history: merged };
        });
        setHasMoreMessages(hasMore);
      } catch (error) {
        if (isMountedRef.current && !cancelled) {
          const activeSelection = selectedConversationRef.current;
          const fallbackPreview = buildPreviewHistory(activeSelection?.conversation);
          const hasAnyFallback = (activeSelection?.history?.length || 0) > 0 || fallbackPreview.length > 0;
          setSelectedConversation((prev) => {
            if (!prev || prev.conversation?.conversation_id !== selectedConversationId) return prev;
            const existing = Array.isArray(prev.history) ? prev.history : [];
            if (existing.length > 0) return prev;
            return { ...prev, history: fallbackPreview };
          });
          setHasMoreMessages(false);
          const msg =
            error instanceof Error && error.name === "AbortError"
              ? "Loading messages timed out - try again"
              : errorMessage(error) || "Failed to load messages. Try again.";
          toast.error(hasAnyFallback ? `${msg} Showing latest available message.` : msg);
        }
      } finally {
        if (isMountedRef.current && !cancelled) {
          setMessagesLoading(false);
        }
      }
    };

    fetchMessages();

    return () => {
      cancelled = true;
      clearTimeout(loadingFallbackTimer);
    };
  }, [selectedConversationId, selectedConversationUserId, useMockData, fetchConversationMessages, mergeWithRecentOperatorMessages, buildPreviewHistory]);

  // Failsafe: if messages stay loading >26s (e.g. request hung), clear loading and notify
  useEffect(() => {
    if (!messagesLoading) {
      messagesLoadingStartRef.current = null;
      return;
    }
    if (!messagesLoadingStartRef.current) messagesLoadingStartRef.current = Date.now();
    const t = setTimeout(() => {
      if (!isMountedRef.current) return;
      const elapsed = messagesLoadingStartRef.current ? Date.now() - messagesLoadingStartRef.current : 0;
      if (elapsed >= 26000) {
        setMessagesLoading(false);
        toast.error("Loading took too long. Try again or reload.");
      }
    }, 26000);
    return () => clearTimeout(t);
  }, [messagesLoading]);


  Object.assign(s, {
    selectedConversationId, selectedConversationUserId,
  });
}
