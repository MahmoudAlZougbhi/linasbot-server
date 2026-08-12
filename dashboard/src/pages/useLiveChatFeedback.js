/* eslint-disable no-unused-vars */
import { useEffect } from "react";
import toast from "react-hot-toast";
import {
  editLiveChatMessage,
  fetchFaqMatchContext,
  faqUpdateAnswer,
  faqCreateFromLivechat,
} from "../utils/liveChatApi";
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

export function useLiveChatFeedback(s) {
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
    handleEndConversation, handleSendMessage, selectedConversationId, selectedConversationUserId,
  } = s;

  /**
   * Feedback handlers
   * @param {LiveChatMessage} message
   * @param {string} feedbackType
   * @returns {void}
   */
  const handleFeedback = (message, feedbackType) => {
    if (!selectedConversation) return;
    if (feedbackType === "good") {
      // Submit positive feedback immediately
      submitFeedback({
        conversation_id: selectedConversation.conversation.conversation_id,
        message_id: message.message_id || message.id || `msg_${Date.now()}`,
        user_question: getPreviousUserMessage(message),
        bot_response: message.content,
        feedback_type: "good",
        language: selectedConversation.conversation.language,
      });
      toast.success("👍 Thanks for your feedback!");
    } else if (feedbackType === "wrong") {
      // Always show FAQ correction pop-up for bot messages (with or without FAQ match)
      setFaqCorrectionModal({ message });
    } else if (feedbackType === "like") {
      // Show modal to edit question + answer and save to FAQ (4 languages)
      setFeedbackModal({
        message,
        feedbackType: "like",
      });
    }
  };

  /**
   * @param {LiveChatMessage} botMessage
   * @returns {string}
   */
  const getPreviousUserMessage = (botMessage) => {
    const messages = selectedConversation?.history || [];
    const botIndex = messages.findIndex((m) => m === botMessage);

    // Find the previous user message
    for (let i = botIndex - 1; i >= 0; i--) {
      const candidate = messages[i];
      if (candidate?.is_user) {
        return asText(candidate.content);
      }
    }

    return "Unknown question";
  };

  /**
   * @param {string} correctAnswer
   * @param {string} feedbackReason
   * @returns {Promise<void>}
   */
  const submitCorrection = async (correctAnswer, feedbackReason) => {
    if (!selectedConversation || !feedbackModal) return;
    const result = await submitFeedback({
      conversation_id: selectedConversation.conversation.conversation_id,
      message_id: feedbackModal.message.id || `msg_${Date.now()}`,
      user_question: getPreviousUserMessage(feedbackModal.message),
      bot_response: feedbackModal.message.content,
      feedback_type: "wrong",
      correct_answer: correctAnswer,
      feedback_reason: feedbackReason,
      language: selectedConversation.conversation.language,
    });

    if (result.success) {
      setFeedbackModal(null);
    }
  };

  /**
   * @param {string} editedQuestion
   * @param {string} editedAnswer
   * @returns {Promise<void>}
   */
  const submitLikeToFaq = async (editedQuestion, editedAnswer) => {
    if (!selectedConversation || !feedbackModal) return;
    const result = await submitFeedback({
      conversation_id: selectedConversation.conversation.conversation_id,
      message_id: feedbackModal.message.id || `msg_${Date.now()}`,
      user_question: editedQuestion,
      bot_response: feedbackModal.message.content,
      feedback_type: "save_to_faq",
      correct_answer: editedAnswer,
      language: selectedConversation.conversation.language,
    });

    if (result.success) {
      setFeedbackModal(null);
      toast.success("Saved to FAQ in 4 languages!");
    }
  };

  useEffect(() => {
    if (editMessageModal?.message) {
      setEditContent(editMessageModal.message.content || "");
    }
  }, [editMessageModal]);

  useEffect(() => {
    if (!faqCorrectionModal?.message || !selectedConversation) {
      setFaqContext(null);
      return;
    }
    const msg = faqCorrectionModal.message;
    const faqMatch = msg.metadata?.faq_match || null;
    if (faqMatch) {
      setFaqContext({ faq_match: faqMatch, current_entry: msg.metadata?.current_entry ?? null });
      setFaqEditAnswer(msg.content || "");
      return;
    }
    setFaqContextLoading(true);
    setFaqEditAnswer(msg.content || "");
    const userId = selectedConversation.conversation.user_id;
    const conversationId = selectedConversation.conversation.conversation_id;
    const messageId = msg.message_id || msg.id || "";
    fetchFaqMatchContext({ userId, conversationId, messageId })
      .then((res) => {
        if (res.success && res.faq_match) {
          setFaqContext({ faq_match: res.faq_match, current_entry: res.current_entry ?? null });
          if (res.current_entry?.answer) setFaqEditAnswer(res.current_entry.answer);
          else setFaqEditAnswer(msg.content || "");
        } else {
          setFaqContext(null);
        }
      })
      .catch(() => setFaqContext(null))
      .finally(() => setFaqContextLoading(false));
  }, [faqCorrectionModal, selectedConversation]);

  const handleFaqSaveChange = async () => {
    if (!faqCorrectionModal?.message || !selectedConversation || !faqContext?.faq_match) return;
    const newAnswer = (faqEditAnswer || "").trim();
    if (!newAnswer) {
      toast.error("Text cannot be empty");
      return;
    }
    setFaqSubmitting(true);
    try {
      const res = await faqUpdateAnswer({
        faqId: faqContext.faq_match.faq_id ?? "",
        newAnswerText: newAnswer,
        updatedBy: operatorId,
        source: "live_chat_dislike",
      });
      if (res.success) {
        const messageId = faqCorrectionModal.message.message_id || faqCorrectionModal.message.id || "";
        await editLiveChatMessage({
          userId: selectedConversation.conversation.user_id,
          conversationId: selectedConversation.conversation.conversation_id,
          messageId,
          newContent: newAnswer,
        });
        setSelectedConversation((prev) => {
          if (!prev?.history) return prev;
          return {
            ...prev,
            history: prev.history.map((m) =>
              (m.message_id || m.id) === messageId ? { ...m, content: newAnswer, text: newAnswer } : m
            ),
          };
        });
        setFaqCorrectionModal(null);
        toast.success("FAQ updated successfully");
      } else {
        toast.error(res.error || "Update failed");
      }
    } catch {
      toast.error("Update failed");
    } finally {
      setFaqSubmitting(false);
    }
  };

  const handleFaqSaveNew = async () => {
    if (!faqCorrectionModal?.message || !selectedConversation) return;
    const newAnswer = (faqEditAnswer || "").trim();
    if (!newAnswer) {
      toast.error("Text cannot be empty");
      return;
    }
    const userQuestion = faqContext?.faq_match?.user_question ?? getPreviousUserMessage(faqCorrectionModal.message);
    const questionLanguage = faqContext?.faq_match?.user_language ?? selectedConversation.conversation.language ?? "ar";
    setFaqSubmitting(true);
    try {
      const res = await faqCreateFromLivechat({
        questionText: userQuestion,
        questionLanguage: questionLanguage === "franco" ? "franco" : questionLanguage,
        answerText: newAnswer,
        createdBy: operatorId,
        source: "live_chat_dislike",
        relatedFaqId: faqContext?.faq_match?.faq_id,
        matchSimilarity: faqContext?.faq_match?.similarity,
      });
      if (res.success) {
        setFaqCorrectionModal(null);
        toast.success("New question added to FAQ");
      } else {
        toast.error(res.error || "Failed to add");
      }
    } catch {
      toast.error("Failed to add");
    } finally {
      setFaqSubmitting(false);
    }
  };

  const submitEditMessage = async () => {
    if (!editMessageModal?.message || !selectedConversation) return;
    const newContent = (editContent || "").trim();
    if (!newContent) {
      toast.error("Text cannot be empty");
      return;
    }
    const msg = editMessageModal.message;
    const messageId = msg.message_id || msg.id || "";
    setIsSubmittingEdit(true);
    try {
      const result = await editLiveChatMessage({
        userId: selectedConversation.conversation.user_id,
        conversationId: selectedConversation.conversation.conversation_id,
        messageId,
        newContent,
      });
      if (result.success) {
        setSelectedConversation((prev) => {
          if (!prev || !prev.history) return prev;
          return {
            ...prev,
            history: prev.history.map((m) =>
              (m.message_id || m.id) === messageId
                ? { ...m, content: newContent, text: newContent }
                : m
            ),
          };
        });
        setEditMessageModal(null);
        toast.success("Reply updated");
      } else {
        toast.error(result.error || "Update failed");
      }
    } catch {
      toast.error("Update failed");
    } finally {
      setIsSubmittingEdit(false);
    }
  };

  Object.assign(s, {
    handleFeedback, getPreviousUserMessage, submitCorrection, submitLikeToFaq, handleFaqSaveChange, handleFaqSaveNew,
    submitEditMessage,
  });
}
