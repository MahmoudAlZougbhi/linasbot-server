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

export function LiveChatDetails(s) {
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
    formatRecordingTime, handleImageSelect, discardImage, sendImageMessage, loadMoreChats, handleBotListScroll,
    handleManualRefresh, formatLastRefreshTime, loadMoreMessages, reloadSelectedConversationMessages, handleTakeOver, handleReleaseToBot,
    handleEndConversation, handleSendMessage, handleFeedback, getPreviousUserMessage, submitCorrection, submitLikeToFaq,
    handleFaqSaveChange, handleFaqSaveNew, submitEditMessage, selectedConversationId, selectedConversationUserId, isBotDateFilterActive, markWaitingConversationRead,
  } = s;
  return (
    <>
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          className={`${sidebarCollapsed ? "col-span-2" : "col-span-3"} whatsapp-info-panel flex flex-col overflow-y-auto p-4`}
        >
          {/* Waiting for human + With operator - taller blocks above user info */}
          <div className="space-y-3 mb-4 flex-shrink-0">
            <div className="whatsapp-info-card p-4">
              <h3 className="font-semibold text-slate-800 text-sm mb-1 flex items-center">
                <span className="mr-1.5">⏳</span>
                Waiting ({filteredWaitingQueue.length})
              </h3>
              {isLoading ? (
                <div className="animate-pulse h-12 bg-slate-100 rounded" />
              ) : (
                <>
                  <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                    {filteredWaitingQueue.length === 0 ? (
                      <p className="text-xs text-slate-400 italic py-1">None</p>
                    ) : (
                      filteredWaitingQueue.map((item) => {
                        const isUserRequested = userRequestedReasons.includes((item.reason || "").toLowerCase());
                        const readKey = `${item.user_id}_${item.conversation_id}`;
                        const readCount = readMessageCountByConv[readKey] ?? 0;
                        const msgCount = item.message_count || 0;
                        // If locally marked read this session, show 0. Else use API unread_count (user msgs only)
                        const unreadCount =
                          readCount > 0 && readCount >= msgCount
                            ? 0
                            : typeof item.unread_count === "number"
                              ? item.unread_count
                              : Math.max(0, msgCount - readCount);
                        return (
                          <div
                            key={item.conversation_id}
                            className={`px-2 py-1.5 rounded cursor-pointer transition-colors text-xs ${
                              isUserRequested
                                ? "bg-orange-50 border border-orange-200 hover:bg-orange-100"
                                : "bg-amber-50 border border-amber-200 hover:bg-amber-100"
                            }`}
                            onClick={() => {
                              markWaitingConversationRead(item.user_id, item.conversation_id, item.message_count || 0);
                              const conv = activeConversations.find(
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
                                last_message:
                                  typeof item.last_message === "string"
                                    ? item.last_message
                                    : item.last_message && typeof item.last_message === "object"
                                      ? {
                                          content:
                                            typeof item.last_message.content === "string"
                                              ? item.last_message.content
                                              : "",
                                        }
                                      : null,
                              };
                              selectConversation(conv);
                            }}
                          >
                            <div className="flex items-center justify-between gap-1">
                              <div className="flex items-center gap-2 min-w-0">
                                <p className="font-medium text-slate-800 truncate">{item.user_name}</p>
                                <NewCustomerBadge isNew={item.is_new_customer} />
                              </div>
                              {unreadCount > 0 && (
                                <span className="text-xs font-bold text-amber-600">{unreadCount}</span>
                              )}
                            </div>
                            <div className="flex items-center justify-between mt-0.5">
                              <span className="text-slate-500">{Math.floor((item.wait_time_seconds || 0) / 60)}m</span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleTakeOver(item.conversation_id, item.user_id);
                                }}
                                className="text-amber-600 hover:text-amber-700 font-medium"
                              >
                                Take Over
                              </button>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </>
              )}
            </div>
            <div className="whatsapp-info-card p-4">
              <h3 className="font-semibold text-slate-800 text-sm mb-1 flex items-center">
                <span className="mr-1.5">💬</span>
                With operator ({filteredWithOperator.length})
              </h3>
              {isLoading ? (
                <div className="animate-pulse h-10 bg-slate-100 rounded" />
              ) : (
                <>
                  <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                    {filteredWithOperator.length === 0 ? (
                      <p className="text-xs text-slate-400 italic py-1">None</p>
                    ) : (
                      filteredWithOperator.map((conv) => {
                        const readKey = `${conv.user_id}_${conv.conversation_id}`;
                        const readCount = readMessageCountByConv[readKey] ?? 0;
                        const msgCount = conv.message_count || 0;
                        // If locally marked read this session, show 0. Else use API unread_count (user msgs only)
                        const unreadCount =
                          readCount > 0 && readCount >= msgCount
                            ? 0
                            : typeof conv.unread_count === "number"
                              ? conv.unread_count
                              : Math.max(0, msgCount - readCount);
                        return (
                          <div
                            key={`${conv.user_id}_${conv.conversation_id}`}
                            className="px-2 py-1.5 rounded cursor-pointer bg-green-50 border border-green-200 hover:bg-green-100 transition-colors text-xs flex items-center justify-between"
                            onClick={() => selectConversation(conv)}
                          >
                            <div className="min-w-0 flex-1 pr-2">
                              <span className="font-medium text-slate-800 truncate block">{conv.user_name}</span>
                              <NewCustomerBadge isNew={conv.is_new_customer} />
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              {unreadCount > 0 && (
                                <span className="inline-flex min-w-[18px] h-[18px] items-center justify-center rounded-full bg-emerald-600 px-1 text-[10px] font-bold text-white">
                                  {unreadCount}
                                </span>
                              )}
                              <SentimentIndicator sentiment={conv.sentiment} />
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
          {selectedConversation ? (
            <div className="space-y-4 flex-1 min-h-0">
              {/* User Info */}
              <div className="whatsapp-info-card">
                <h3 className="font-bold text-slate-800 mb-3 flex items-center">
                  <UserIcon className="w-5 h-5 mr-2 text-primary-600" />
                  User Information
                </h3>
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-slate-500">Name</p>
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-slate-800">
                        {selectedConversation.conversation.user_name}
                      </p>
                      <NewCustomerBadge isNew={selectedConversation.conversation.is_new_customer} />
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Phone</p>
                    <p className="font-medium text-slate-800">
                      {formatPhoneForDisplay(selectedConversation.conversation.user_phone)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Language</p>
                    <p className="font-medium text-slate-800">
                      {(selectedConversation.conversation.language || "").toUpperCase()}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Gender</p>
                    <p className="font-medium text-slate-800 capitalize">
                      {selectedConversation.conversation.gender || "Unknown"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Sentiment</p>
                    <div className="flex items-center space-x-2">
                      <SentimentIndicator sentiment={selectedConversation.conversation.sentiment} />
                      <span className="font-medium text-slate-800 capitalize">
                        {selectedConversation.conversation.sentiment}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Conversation Stats */}
              <div className="whatsapp-info-card">
                <h3 className="font-bold text-slate-800 mb-3 flex items-center">
                  <ChartBarIcon className="w-5 h-5 mr-2 text-secondary-600" />
                  Conversation Stats
                </h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Messages</span>
                    <span className="font-medium text-slate-800">
                      {selectedConversation.conversation.message_count}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Duration</span>
                    <span className="font-medium text-slate-800">
                      {(() => {
                        const durationSeconds =
                          Number(selectedConversation.conversation.duration_seconds) || 0;
                        return `${Math.floor(durationSeconds / 60)}m ${durationSeconds % 60}s`;
                      })()}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Status</span>
                    <StatusBadge status={selectedConversation.conversation.status} />
                  </div>
                  {selectedConversation.conversation.operator_id && (
                    <div className="flex justify-between">
                      <span className="text-sm text-slate-600">Operator</span>
                      <span className="font-medium text-slate-800">
                        {selectedConversation.conversation.operator_id}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Quick Actions */}
              <div className="whatsapp-info-card">
                <h3 className="font-bold text-slate-800 mb-3">Quick Actions</h3>
                <div className="space-y-2">
                  <button
                    onClick={() =>
                      handleEndConversation(
                        selectedConversation.conversation.conversation_id,
                        selectedConversation.conversation.user_id
                      )
                    }
                    className="w-full btn-ghost text-left text-sm text-red-600 hover:bg-red-50"
                  >
                    <XMarkIcon className="w-4 h-4 mr-2" />
                    End Conversation
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="card p-4">
              <p className="text-center text-slate-500">
                Select a conversation to view details
              </p>
            </div>
          )}
        </motion.div>

    </>
  );
}
