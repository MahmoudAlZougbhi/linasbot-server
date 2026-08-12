/* eslint-disable no-unused-vars */
import { useEffect } from "react";
import toast from "react-hot-toast";
import { errorMessage } from "../utils/apiValidate";
import { endLiveChatConversation } from "../utils/liveChatApi";
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

export function useLiveChatActions(s) {
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
    handleManualRefresh, formatLastRefreshTime, loadMoreMessages, reloadSelectedConversationMessages, handleFeedback, getPreviousUserMessage,
    submitCorrection, submitLikeToFaq, handleFaqSaveChange, handleFaqSaveNew, submitEditMessage, selectedConversationId,
    selectedConversationUserId,
  } = s;

  // Auto-scroll: when chat opens go to last message (bottom); when near bottom and new messages, scroll.
  useEffect(() => {
    const conversationId = selectedConversation?.conversation?.conversation_id || null;
    const messageCount = selectedConversation?.history?.length || 0;
    const previousConversationId = previousConversationIdRef.current;
    const previousMessageCount = previousMessageCountRef.current;

    const hasConversationChanged =
      conversationId && conversationId !== previousConversationId;
    const hasNewMessages = messageCount > previousMessageCount;
    const isFirstLoadForConversation = messageCount > 0 && previousMessageCount === 0;

    const container = messagesContainerRef.current;
    const shouldForceBottom =
      conversationId && forceBottomOnOpenRef.current === conversationId;
    const nearBottom = container
      ? container.scrollHeight - container.scrollTop - container.clientHeight < 120
      : true;

    const shouldScrollToBottomOnOpen =
      hasConversationChanged || isFirstLoadForConversation || shouldForceBottom;
    const shouldScrollForNewMessages =
      hasNewMessages && (nearBottom || shouldForceBottom);

    previousConversationIdRef.current = conversationId;
    previousMessageCountRef.current = messageCount;

    if (shouldScrollToBottomOnOpen || shouldScrollForNewMessages) {
      const behavior = shouldScrollToBottomOnOpen ? "auto" : "smooth";
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
      messagesEndRef.current?.scrollIntoView({ behavior });
      // When opening a conversation, messages may render after this effect — scroll again after paint.
      if (shouldScrollToBottomOnOpen || shouldForceBottom) {
        const rafId = requestAnimationFrame(() => {
          if (container) {
            container.scrollTop = container.scrollHeight;
          }
          messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
        });
        const settleId = setTimeout(() => {
          if (
            forceBottomOnOpenRef.current === conversationId &&
            messageCount > 0
          ) {
            forceBottomOnOpenRef.current = null;
          }
        }, 400);
        return () => {
          cancelAnimationFrame(rafId);
          clearTimeout(settleId);
        };
      }
    }
  }, [selectedConversation?.conversation?.conversation_id, selectedConversation?.history?.length]);

  /**
   * @param {string} conversationId
   * @param {string} userId
   * @returns {Promise<void>}
   */
  const handleTakeOver = async (conversationId, userId) => {
    console.log("🔄 handleTakeOver called with:", { conversationId, userId });

    if (!conversationId || !userId) {
      console.error("❌ Missing conversationId or userId:", { conversationId, userId });
      toast.error("Cannot take over: missing conversation or user ID");
      return;
    }
    if (isSocialChannelUser(userId, selectedConversation?.conversation?.channel)) {
      toast.error("Instagram/Facebook conversations are read-only. Use WhatsApp handoff links.");
      return;
    }

    try {
      const result = await takeoverConversation(
        conversationId,
        userId,
        operatorId
      )

      console.log("📋 Takeover result:", result);

      if (result.success) {
        toast.success("Conversation taken over successfully");
        // Update conversation status locally
        setActiveConversations((prev) => {
          const exists = prev.some((conv) => conv.conversation_id === conversationId && conv.user_id === userId);
          const updated = prev.map((conv) =>
            conv.conversation_id === conversationId && conv.user_id === userId
              ? { ...conv, status: "human", operator_id: operatorId }
              : conv
          );
          if (exists) return updated;
          const fallback = selectedConversation?.conversation &&
            selectedConversation.conversation.conversation_id === conversationId
            ? selectedConversation.conversation
            : null;
          /** @type {LiveChatConversation} */
          const newEntry = {
            ...(fallback || {
              conversation_id: conversationId,
              user_id: userId,
              user_name: userId,
              user_phone: "",
              status: "human",
              language: "ar",
              sentiment: "neutral",
              message_count: 0,
            }),
            status: "human",
            operator_id: operatorId,
          };
          return [newEntry, ...updated];
        });
        // Update selected conversation if it's the one we took over
        if (
          selectedConversation?.conversation?.conversation_id === conversationId
        ) {
          setSelectedConversation((prev) =>
            prev
              ? {
                  ...prev,
                  conversation: {
                    ...prev.conversation,
                    status: "human",
                    operator_id: operatorId,
                  },
                }
              : prev
          );
        }
        // Remove from waiting queue (match by both user_id and conversation_id)
        setWaitingQueue((prev) =>
          prev.filter(
            (item) =>
              !(item.conversation_id === conversationId && item.user_id === userId)
          )
        );
      } else {
        console.error("❌ Takeover failed:", result.error);
        toast.error(`Failed to take over: ${result.error || "Unknown error"}`);
      }
    } catch (error) {
      console.error("❌ Error taking over conversation:", error);
      toast.error(`Error: ${errorMessage(error) || "Unknown error"}`);
    }
  };

  /**
   * @param {string} conversationId
   * @param {string} userId
   * @returns {Promise<void>}
   */
  const handleReleaseToBot = async (conversationId, userId) => {
    if (releasingRef.current || isReleasing) return;
    releasingRef.current = true;
    setIsReleasing(true);
    try {
      const result = await releaseConversation(conversationId, userId);

      if (result?.success) {
        toast.success("Conversation released to bot!");
        const postRelUntil = new Date(Date.now() + 45 * 60 * 1000).toISOString();
        // Update conversation status locally
        setActiveConversations((prev) =>
          prev.map((conv) =>
            conv.conversation_id === conversationId && conv.user_id === userId
              ? {
                  ...conv,
                  status: "bot",
                  operator_id: null,
                  human_takeover_active: false,
                  post_release_escalation_suppressed_until: postRelUntil,
                  conversation_state: "bot_active",
                }
              : conv
          )
        );
        setWaitingQueue((prev) =>
          prev.filter(
            (item) =>
              !(item.conversation_id === conversationId && item.user_id === userId)
          )
        );
        // Update selected conversation if it's the one we released
        if (
          selectedConversation?.conversation?.conversation_id === conversationId
        ) {
          setSelectedConversation((prev) =>
            prev
              ? {
                  ...prev,
                  conversation: {
                    ...prev.conversation,
                    status: "bot",
                    operator_id: null,
                    human_takeover_active: false,
                    post_release_escalation_suppressed_until: postRelUntil,
                    conversation_state: "bot_active",
                  },
                }
              : prev
          );
        }
      } else {
        const errMsg = result?.error ? `Failed to release: ${result.error}` : "Failed to release conversation";
        toast.error(errMsg);
      }
    } catch (error) {
      console.error("Error releasing conversation:", error);
      toast.error("Error releasing conversation");
    } finally {
      releasingRef.current = false;
      setIsReleasing(false);
    }
  };

  /**
   * @param {string} conversationId
   * @param {string} userId
   * @returns {Promise<void>}
   */
  const handleEndConversation = async (conversationId, userId) => {
    try {
      const result = await endLiveChatConversation({
        conversationId,
        userId,
        operatorId: operatorId,
      });

      if (result.success) {
        toast.success("Conversation ended successfully");
        // Remove from active conversations
        setActiveConversations((prev) =>
          prev.filter((conv) => conv.conversation_id !== conversationId)
        );
        // Clear selection if it was the ended conversation
        if (
          selectedConversation?.conversation?.conversation_id === conversationId
        ) {
          setSelectedConversation(null);
        }
      } else {
        toast.error("Failed to end conversation");
      }
    } catch (error) {
      console.error("Error ending conversation:", error);
      toast.error("Error ending conversation");
    }
  };

  const handleSendMessage = async () => {
    if (!messageInput.trim() || !selectedConversation || isSending || sendingRef.current) return;
    if (isSocialChannelUser(selectedConversation.conversation?.user_id, selectedConversation.conversation?.channel)) {
      toast.error("Instagram/Facebook conversations are read-only. Use WhatsApp handoff links.");
      return;
    }

    sendingRef.current = true;
    setIsSending(true);
    const messageToSend = messageInput.trim();
    setMessageInput(""); // Clear immediately to prevent duplicate sends

    // Optimistic append BEFORE API call so it's in state when SSE arrives (prevents double display).
    // If we append after API: SSE can arrive first → add message → API returns → append again = duplicate.
    const optimisticMessage = {
      message_id: `local_op_${Date.now()}`,
      timestamp: new Date().toISOString(),
      is_user: false,
      role: "operator",
      handled_by: "human",
      type: "text",
      content: messageToSend,
      text: messageToSend,
    };
    appendMessageToSelectedConversation(optimisticMessage);
    saveOperatorMessageToSession(
      selectedConversation.conversation.user_id,
      selectedConversation.conversation.conversation_id,
      optimisticMessage
    );
    updateChatListLocally(
      selectedConversation.conversation.conversation_id,
      selectedConversation.conversation.user_id,
      optimisticMessage
    );

    const idempotencyKey =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `op_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;

    try {
      const result = await sendOperatorMessage(
        selectedConversation.conversation.conversation_id,
        selectedConversation.conversation.user_id,
        messageToSend,
        operatorId,
        "text",
        idempotencyKey
      );

      if (result.success) {
        toast.success("Message sent to customer");
      } else {
        toast.error("Failed to send message");
        // Rollback optimistic message on failure
        setSelectedConversation((prev) => {
          if (!prev?.history) return prev;
          const filtered = prev.history.filter((m) => m.message_id !== optimisticMessage.message_id);
          if (messageCacheRef?.current && prev.conversation) {
            const cacheKey = `${prev.conversation.user_id}_${prev.conversation.conversation_id}`;
            const existing = messageCacheRef.current.get(cacheKey);
            messageCacheRef.current.set(cacheKey, {
              messages: filtered,
              hasMore: existing?.hasMore ?? false,
              cachedAt: Date.now(),
              isPartial: existing?.isPartial ?? false,
            });
          }
          return { ...prev, history: filtered };
        });
      }
    } catch (error) {
      console.error("Error sending message:", error);
      toast.error("Error sending message");
      // Rollback optimistic message on error
      setSelectedConversation((prev) => {
        if (!prev?.history) return prev;
        const filtered = prev.history.filter((m) => m.message_id !== optimisticMessage.message_id);
        if (messageCacheRef?.current && prev.conversation) {
          const cacheKey = `${prev.conversation.user_id}_${prev.conversation.conversation_id}`;
          const existing = messageCacheRef.current.get(cacheKey);
          messageCacheRef.current.set(cacheKey, {
            messages: filtered,
            hasMore: existing?.hasMore ?? false,
            cachedAt: Date.now(),
            isPartial: existing?.isPartial ?? false,
          });
        }
        return { ...prev, history: filtered };
      });
    } finally {
      setIsSending(false);
      sendingRef.current = false;
    }
  };

  Object.assign(s, {
    handleTakeOver, handleReleaseToBot, handleEndConversation, handleSendMessage,
  });
}
