/* eslint-disable no-unused-vars */
import { motion } from "framer-motion";
import {
  ChatBubbleLeftRightIcon,
  UserIcon,
  PhoneIcon,
  GlobeAltIcon,
  HandRaisedIcon,
  ExclamationCircleIcon,
  ArrowRightIcon,
  PaperAirplaneIcon,
  UserGroupIcon,
  XMarkIcon,
  ChartBarIcon,
  MicrophoneIcon,
  PhotoIcon,
  MagnifyingGlassIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from "@heroicons/react/24/outline";
import FeedbackModal from "../components/FeedbackModal";
import LikeFeedbackModal from "../components/LikeFeedbackModal";
import ModernAudioPlayer from "../components/LiveChat/ModernAudioPlayer";
import {
  SentimentIndicator,
  StatusBadge,
  NewCustomerBadge,
} from "../components/LiveChat/ConversationIndicators";
import { formatMessageTime } from "../utils/dateUtils";
import { lastMessageContent } from "./LiveChat.helpers";

export function LiveChatThreadHeader(s) {
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
    handleFaqSaveChange, handleFaqSaveNew, submitEditMessage, selectedConversationId, selectedConversationUserId, isBotDateFilterActive, markWaitingConversationRead,
  } = s;
  return (
    <>
              {/* Chat Header - Fixed Height */}
              <div className="whatsapp-chat-header">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    {sidebarCollapsed && (
                      <button
                        onClick={() => setBotPanelOpen((o) => !o)}
                        className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm font-medium text-slate-700 mr-2"
                        title="With bot conversations"
                      >
                        <ChatBubbleLeftRightIcon className="w-4 h-4 text-primary-600" />
                        With bot ({filteredBotConversations.length})
                      </button>
                    )}
                    <div className="w-10 h-10 bg-gradient-to-r from-primary-400 to-secondary-400 rounded-full flex items-center justify-center text-white font-bold">
                      {(selectedConversation.conversation.user_name || "?").charAt(0)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-bold text-slate-800">
                          {selectedConversation.conversation.user_name}
                        </p>
                        <NewCustomerBadge isNew={selectedConversation.conversation.is_new_customer} />
                      </div>
                      <div className="flex items-center space-x-3 text-xs text-slate-500">
                        <span className="flex items-center">
                          <PhoneIcon className="w-3 h-3 mr-1" />
                          {formatPhoneForDisplay(selectedConversation.conversation.user_phone || selectedConversation.conversation.phone_number || "")}
                        </span>
                        <span className="flex items-center">
                          <GlobeAltIcon className="w-3 h-3 mr-1" />
                          {(selectedConversation.conversation.language || "ar").toUpperCase()}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2">
                    {selectedConversation.conversation.status === "bot" ? (
                      <button
                        onClick={() =>
                          handleTakeOver(
                            selectedConversation.conversation.conversation_id,
                            selectedConversation.conversation.user_id
                          )
                        }
                        className="whatsapp-pill"
                      >
                        <HandRaisedIcon className="w-4 h-4 mr-1" />
                        Take Over
                      </button>
                    ) : (
                      selectedConversation.conversation.status === "human" && (
                        <button
                          onClick={() =>
                            handleReleaseToBot(
                              selectedConversation.conversation.conversation_id,
                              selectedConversation.conversation.user_id
                            )
                          }
                          disabled={isReleasing}
                          className="whatsapp-pill-outline"
                        >
                          <ArrowRightIcon className="w-4 h-4 mr-1" />
                          {isReleasing ? "Releasing..." : "Release to Bot"}
                        </button>
                      )
                    )}
                    <StatusBadge status={selectedConversation.conversation.status} />

                    {/* ✅ Reload Messages Button */}
                    <button
                      onClick={reloadSelectedConversationMessages}
                      title="Reload conversation messages"
                      className="p-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 hover:text-slate-700 transition-all"
                    >
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                        />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>

    </>
  );
}
