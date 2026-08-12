/* eslint-disable no-unused-vars */
import { useCallback, useEffect } from "react";
import toast from "react-hot-toast";
import { getAxiosErrorCode } from "../utils/apiValidate";
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

export function useLiveChatPaging(s) {
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
    applyTemplateSendFilter, clearTemplateSendFilter, fetchConversationMessages, getRecentOpFromSession, saveOperatorMessageToSession, mergeWithRecentOperatorMessages,
    buildPreviewHistory, getConversationUnreadCount, buildConversationFromQueueItem, selectConversation, openConversation, openWaitingConversation,
    appendMessageToSelectedConversation, updateChatListLocally, isRecording, recordedAudio, recordingTime, isSendingVoice,
    selectedImage, imageInputRef, startRecording, stopRecording, discardRecording, sendVoiceMessage,
    formatRecordingTime, handleImageSelect, discardImage, sendImageMessage, handleTakeOver, handleReleaseToBot,
    handleEndConversation, handleSendMessage, handleFeedback, getPreviousUserMessage, submitCorrection, submitLikeToFaq,
    handleFaqSaveChange, handleFaqSaveNew, submitEditMessage, selectedConversationId, selectedConversationUserId,
  } = s;

  const loadMoreChats = useCallback(async () => {
    if (templateSendFilterActive && templateSendFilterId) return;
    if (loadingMoreChats || !hasMoreChats || loadMoreInProgressRef.current) return;
    if (Date.now() < loadMoreCooldownUntilRef.current) return;
    if (!nextCursor) return; // Backend uses cursor-based pagination; need cursor for next page
    loadMoreInProgressRef.current = true;
    setLoadingMoreChats(true);
    try {
      /** @type {string | null} */
      let cursor = nextCursor;
      /** @type {boolean} */
      let hasMore = hasMoreChats;
      let pagesFetched = 0;
      let totalAdded = 0;
      const seenKeys = new Set(
        activeConversationsRef.current.map((c) => `${c.user_id}_${c.conversation_id}`)
      );

      // Fetch up to 3 pages in one go to skip duplicate-only pages.
      while (cursor && hasMore && pagesFetched < 3) {
        const chatsResponse = await getUnifiedChats(
          debouncedSearch,
          1,
          CHAT_LIST_PAGE_SIZE,
          cursor
        );
        pagesFetched += 1;
        if (!chatsResponse?.success) break;

        const normalized = asConversationList(chatsResponse.chats)
          .map(normalizeIncomingConversation)
          .filter(isConversation);
        const deduped = normalized.filter((c) => {
          const key = `${c.user_id}_${c.conversation_id}`;
          if (seenKeys.has(key)) return false;
          seenKeys.add(key);
          return true;
        });

        if (deduped.length > 0) {
          totalAdded += deduped.length;
          setActiveConversations((prev) => [...prev, ...deduped]);
        }

        cursor = chatsResponse.next_cursor || null;
        hasMore = Boolean(chatsResponse.has_more && cursor);

        // If we got new chats, stop here and let next user scroll load more.
        if (totalAdded > 0) break;
      }

      setNextCursor(cursor || null);
      setChatPage((p) => p + pagesFetched);
      setHasMoreChats(Boolean(hasMore));
      loadMoreCooldownUntilRef.current = Date.now() + 1500; // Cooldown 1.5s
    } catch (error) {
      console.error("Error loading more chats:", error);
      loadMoreCooldownUntilRef.current = Date.now() + 2000; // Cooldown on error too
    } finally {
      loadMoreInProgressRef.current = false;
      setLoadingMoreChats(false);
    }
  }, [
    loadingMoreChats,
    hasMoreChats,
    nextCursor,
    getUnifiedChats,
    debouncedSearch,
    normalizeIncomingConversation,
    templateSendFilterActive,
    templateSendFilterId,
  ]);

  const handleBotListScroll = useCallback(
    /**
     * @param {import('react').UIEvent<HTMLDivElement>} event
     * @returns {void}
     */
    (event) => {
      const el = event.currentTarget;
      if (templateSendFilterActive && templateSendFilterId) return;
      if (!el || loadingMoreChats || !hasMoreChats || loadMoreInProgressRef.current) return;
      if (botListScrollThrottleRef.current || Date.now() < loadMoreCooldownUntilRef.current) return;
      if (!nextCursor) return;
      const threshold = 280;
      const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (distanceToBottom <= threshold) {
        botListScrollThrottleRef.current = true;
        loadMoreChats();
        setTimeout(() => {
          botListScrollThrottleRef.current = false;
        }, 800);
      }
    },
    [
      loadingMoreChats,
      hasMoreChats,
      nextCursor,
      loadMoreChats,
      templateSendFilterActive,
      templateSendFilterId,
    ]
  );

  // Intersection Observer: load more when sentinel comes into view (avoid filteredBotConversations.length in deps to prevent loop)
  useEffect(() => {
    if (templateSendFilterActive && templateSendFilterId) return;
    const sentinel = botLoadMoreSentinelRef.current;
    const scrollRoot = botListRef.current;
    if (!sentinel || !scrollRoot || !hasMoreChats || loadingMoreChats) return;
    const obs = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;
        if (!entry?.isIntersecting || loadMoreInProgressRef.current) return;
        if (Date.now() < loadMoreCooldownUntilRef.current) return;
        loadMoreChats();
      },
      { root: scrollRoot, rootMargin: "200px", threshold: 0.1 }
    );
    obs.observe(sentinel);
    return () => obs.disconnect();
  }, [
    hasMoreChats,
    loadingMoreChats,
    loadMoreChats,
    templateSendFilterActive,
    templateSendFilterId,
  ]);

  // Auto-load extra pages to reduce missing conversations on first load
  useEffect(() => {
    if (debouncedSearch.trim()) {
      autoLoadedPagesRef.current = 1;
      return;
    }
    if (!hasMoreChats || loadingMoreChats || !nextCursor) return;
    if (activeConversations.length >= 60) return;
    if (autoLoadedPagesRef.current >= 2) return;
    if (Date.now() < loadMoreCooldownUntilRef.current) return;
    autoLoadedPagesRef.current += 1;
    loadMoreChats();
  }, [debouncedSearch, hasMoreChats, loadingMoreChats, nextCursor, activeConversations.length, loadMoreChats]);

  // ✅ Manual refresh handler
  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    try {
      const [chatsResult, queueResult] = await Promise.allSettled([
        getUnifiedChats(debouncedSearch, 1, CHAT_LIST_PAGE_SIZE),
        getWaitingQueue(),
      ]);

      let chatsResponse =
        chatsResult.status === "fulfilled" ? chatsResult.value : null;

      if (!chatsResponse?.success) {
        try {
          const fallback = await getLiveConversations(debouncedSearch);
          if (fallback?.success && Array.isArray(fallback.conversations)) {
            chatsResponse = {
              success: true,
              chats: fallback.conversations,
              has_more: false,
            };
          }
        } catch (fallbackErr) {
          console.warn("Live Chat manual refresh fallback error:", fallbackErr);
        }
      }

      if (chatsResponse?.success && chatsResponse.chats) {
        let chats = asConversationList(chatsResponse.chats);
        const selected = selectedConversationRef.current?.conversation;
        if (selected) {
          const alreadyInList = chats.some(
            (c) => c.conversation_id === selected.conversation_id && c.user_id === selected.user_id
          );
          if (!alreadyInList) {
            chats = [selected, ...chats];
          }
        }

        const previousIds = new Set(
          activeConversationsRef.current.map((c) => c.conversation_id)
        );
        const newIds = new Set(
          chats.filter((c) => !previousIds.has(c.conversation_id)).map((c) => c.conversation_id)
        );

        applyServerConversations(chats);
        setChatPage(1);
        setNextCursor(chatsResponse.next_cursor ?? null);
        setHasMoreChats(chatsResponse.has_more || false);
        setNewConversationIds(newIds);
        setLastRefreshTime(new Date());
        autoLoadedPagesRef.current = 1;
        toast.success("Conversations refreshed");

        // Auto-clear "new" badge after 10 seconds
        if (newIds.size > 0) {
          setTimeout(() => setNewConversationIds(new Set()), 10000);
        }
      }

      if (queueResult.status === "fulfilled" && queueResult.value?.success) {
        applyWaitingQueue(queueResult.value);
      }
      if (!chatsResponse?.success) {
        toast.error("Failed to refresh conversations");
      }

      if (chatsResult.status === "rejected") {
        console.warn("Live Chat manual refresh error:", chatsResult.reason);
      }
      if (queueResult.status === "rejected") {
        console.warn("Live Chat queue refresh error:", queueResult.reason);
      }
    } catch (error) {
      console.error("Error refreshing conversations:", error);
      if (getAxiosErrorCode(error) === "ECONNABORTED") {
        toast.error("Request timeout - server may be busy. Try again.");
      } else {
        toast.error("Failed to refresh conversations");
      }
    } finally {
      setIsRefreshing(false);
    }
  };

  /**
   * ✅ Format last refresh time as relative time (e.g., "2 seconds ago")
   * @returns {string}
   */
  const formatLastRefreshTime = () => {
    const diff = Math.floor((Date.now() - (lastRefreshTime?.getTime() ?? Date.now())) / 1000); // seconds

    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  };

  // ✅ Load more = next 30 messages (day_window=0 = no day limit, fast load)
  const loadMoreMessages = async () => {
    if (!selectedConversation || loadingMoreMessages || !hasMoreMessages) return;
    const history = selectedConversation.history || [];
    const sorted = [...history].sort(
      (a, b) => new Date(a?.timestamp || 0).getTime() - new Date(b?.timestamp || 0).getTime()
    );
    const beforeTs = sorted.length > 0 && sorted[0]?.timestamp
      ? sorted[0].timestamp
      : new Date().toISOString();
    setLoadingMoreMessages(true);
    try {
      const { messages: older, hasMore } = await fetchConversationMessages(
        selectedConversation.conversation.user_id,
        selectedConversation.conversation.conversation_id,
        0,
        beforeTs,
        0,
        30
      );
      if (older && older.length > 0) {
        // Prepend older messages; dedupe by message_id
        setSelectedConversation((prev) => {
          const prevHistory = prev?.history || [];
          const seen = new Set(prevHistory.map((m) => m.message_id).filter(Boolean));
          const newOlder = older.filter((m) => !m.message_id || !seen.has(m.message_id));
          const combined = [...newOlder, ...prevHistory];
          const deduped = combined
            .filter((m, i, arr) => {
              const id = m.message_id;
              if (!id) return true;
              return arr.findIndex((x) => x.message_id === id) === i;
            })
            .sort((a, b) => new Date(a?.timestamp || 0).getTime() - new Date(b?.timestamp || 0).getTime());
          if (selectedConversation?.conversation) {
            const key = `${selectedConversation.conversation.user_id}_${selectedConversation.conversation.conversation_id}`;
            messageCacheRef.current.set(key, {
              messages: deduped,
              hasMore,
              cachedAt: Date.now(),
              isPartial: false,
            });
          }
          return prev ? { ...prev, history: deduped } : prev;
        });
      }
      setHasMoreMessages(hasMore);
    } catch (e) {
      console.error("Load more messages error:", e);
    } finally {
      setLoadingMoreMessages(false);
    }
  };

  // ✅ Reload messages for currently selected conversation (all history, no day limit)
  const reloadSelectedConversationMessages = async () => {
    if (!selectedConversation) return;

    const key = `${selectedConversation.conversation.user_id}_${selectedConversation.conversation.conversation_id}`;
    try {
      const { messages, hasMore } = await fetchConversationMessages(
        selectedConversation.conversation.user_id,
        selectedConversation.conversation.conversation_id,
        0,
        null,
        0,
        30
      );
      const merged = mergeWithRecentOperatorMessages(messages || [], key);
      setSelectedConversation((prev) => (prev ? { ...prev, history: merged } : prev));
      setHasMoreMessages(hasMore);
      messageCacheRef.current.set(key, {
        messages: merged,
        hasMore: hasMore || false,
        cachedAt: Date.now(),
        isPartial: false,
      });
      toast.success(`Loaded ${merged.length} messages`);
    } catch (error) {
      console.error("Error reloading conversation messages:", error);
      toast.error("Failed to reload messages");
    }
  };

  Object.assign(s, {
    loadMoreChats, handleBotListScroll, handleManualRefresh, formatLastRefreshTime, loadMoreMessages, reloadSelectedConversationMessages,
  });
}
