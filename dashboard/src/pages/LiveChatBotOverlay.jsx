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

export function LiveChatBotOverlay(s) {
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
  if (!sidebarCollapsed || !botPanelOpen) return null;
  return (
                <>
                  <div
                    className="fixed inset-0 z-30 bg-black/20"
                    onClick={() => setBotPanelOpen(false)}
                    aria-hidden="true"
                  />
                  <motion.div
                    initial={{ x: -320 }}
                    animate={{ x: 0 }}
                    exit={{ x: -320 }}
                    className="fixed left-0 top-0 bottom-0 w-80 z-40 bg-white border-r border-slate-200 shadow-xl flex flex-col overflow-hidden"
                  >
                    <div className="p-4 border-b border-slate-200 flex items-center justify-between">
                      <h3 className="font-bold text-slate-800 flex items-center">
                        <ChatBubbleLeftRightIcon className="w-5 h-5 mr-2 text-primary-600" />
                        {templateSendFilterViewActive ? (
                          <>
                            Template: {templateSendFilterLabel} ({filteredBotConversations.length})
                          </>
                        ) : (
                          <>With bot ({filteredBotConversations.length})</>
                        )}
                      </h3>
                      <button
                        onClick={() => setBotPanelOpen(false)}
                        className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
                      >
                        <XMarkIcon className="w-5 h-5" />
                      </button>
                    </div>
                    <div
                      ref={botFloatingScrollRef}
                      className="flex-1 overflow-y-auto p-3"
                      onScroll={handleBotListScroll}
                    >
                      <div className="relative mb-3">
                        <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                        <input
                          type="text"
                          value={liveSearchQuery}
                          onChange={(e) => setLiveSearchQuery(e.target.value)}
                          placeholder="Search by name or phone..."
                          className="whatsapp-input w-full pl-9 pr-4"
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-2 mb-2">
                        <input
                          type="date"
                          value={botDateFrom}
                          onChange={(e) => setBotDateFrom(e.target.value)}
                          className="whatsapp-input w-full px-3 py-1.5 text-xs"
                          title="From date"
                        />
                        <input
                          type="date"
                          value={botDateTo}
                          onChange={(e) => setBotDateTo(e.target.value)}
                          className="whatsapp-input w-full px-3 py-1.5 text-xs"
                          title="To date"
                        />
                      </div>
                      <select
                        value={templateSendFilterId}
                        onChange={(e) => setTemplateSendFilterId(e.target.value)}
                        className="whatsapp-input w-full px-2 py-1.5 text-xs mb-2"
                        disabled={templateSendFilterLoading}
                      >
                        <option value="">Template filter…</option>
                        {Object.keys(messagingTemplates)
                          .sort()
                          .map((tid) => (
                            <option key={tid} value={tid}>
                              {(messagingTemplates[tid]?.name || tid).slice(0, 60)}
                            </option>
                          ))}
                      </select>
                      <div className="flex gap-2 mb-3">
                        <button
                          type="button"
                          disabled={templateSendFilterLoading}
                          onClick={() => applyTemplateSendFilter()}
                          className="text-xs px-2 py-1 rounded border border-violet-200 bg-violet-50 text-violet-800 flex-1 disabled:opacity-50"
                        >
                          Apply
                        </button>
                        <button
                          type="button"
                          onClick={() => clearTemplateSendFilter()}
                          className="text-xs px-2 py-1 rounded border border-slate-200 text-slate-600"
                        >
                          Clear
                        </button>
                      </div>
                      <div className="space-y-2">
                        {liveBotConversations.length > 0 && (
                          <div className="pt-1">
                            <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">Live now</p>
                            <div className="space-y-2">
                              {liveBotConversations.map((conv) => (
                                <div
                                  key={`${conv.user_id}_${conv.conversation_id}`}
                                  className={`p-3 rounded-lg cursor-pointer transition-all ${
                                    selectedConversation?.conversation?.conversation_id === conv.conversation_id
                                      ? "bg-primary-50 border-2 border-primary-300"
                                      : "bg-slate-50 border border-slate-200 hover:bg-slate-100"
                                  }`}
                                  onClick={() => {
                                    selectConversation(conv);
                                    setBotPanelOpen(false);
                                  }}
                                >
                                  <div className="flex items-start justify-between mb-1">
                                    <div className="flex items-center gap-2">
                                    <p className="font-medium text-slate-800 text-sm truncate">{conv.user_name}</p>
                                    <NewCustomerBadge isNew={conv.is_new_customer} />
                                  </div>
                                    <SentimentIndicator sentiment={conv.sentiment} />
                                  </div>
                                  <p className="text-xs text-slate-500 truncate">{formatPhoneForDisplay(conv.user_phone || conv.phone_number || "")}</p>
                                  <p className="text-[11px] text-slate-400 mt-1">{formatConversationListDate(conv)}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {historyBotConversations.length > 0 && (
                          <div className="pt-3">
                            <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">Earlier</p>
                            <div className="space-y-2">
                              {historyBotConversations.map((conv) => (
                                <div
                                  key={`${conv.user_id}_${conv.conversation_id}`}
                                  className={`p-3 rounded-lg cursor-pointer transition-all ${
                                    selectedConversation?.conversation?.conversation_id === conv.conversation_id
                                      ? "bg-primary-50 border-2 border-primary-300"
                                      : "bg-slate-50 border border-slate-200 hover:bg-slate-100"
                                  }`}
                                  onClick={() => {
                                    selectConversation(conv);
                                    setBotPanelOpen(false);
                                  }}
                                >
                                  <div className="flex items-start justify-between mb-1">
                                    <div className="flex items-center gap-2">
                                      <p className="font-medium text-slate-800 text-sm truncate">{conv.user_name}</p>
                                      <NewCustomerBadge isNew={conv.is_new_customer} />
                                    </div>
                                    <SentimentIndicator sentiment={conv.sentiment} />
                                  </div>
                                  <p className="text-xs text-slate-500 truncate">{formatPhoneForDisplay(conv.user_phone || conv.phone_number || "")}</p>
                                  <p className="text-[11px] text-slate-400 mt-1">{formatConversationListDate(conv)}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {hasMoreChats && (
                          <button
                            onClick={loadMoreChats}
                            disabled={loadingMoreChats}
                            className="w-full py-2 mt-2 text-sm font-medium text-primary-600 hover:bg-primary-50 rounded-lg border border-primary-200 transition disabled:opacity-60"
                          >
                            {loadingMoreChats ? (
                              <span className="inline-flex items-center gap-2">
                                <span className="inline-block w-4 h-4 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
                                Loading...
                              </span>
                            ) : (
                              "Load More"
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  </motion.div>
                </>

  );
}
