/* eslint-disable no-unused-vars */
import toast from "react-hot-toast";
import { motion } from "framer-motion";
import { errorMessage } from "../utils/apiValidate";
import { CHAT_LIST_PAGE_SIZE } from "./LiveChat.helpers";
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

export function LiveChatSidebar(s) {
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
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className={`${sidebarCollapsed ? "col-span-1" : "col-span-3"} whatsapp-sidebar flex flex-col overflow-hidden transition-all min-w-0`}
        >
          {sidebarCollapsed ? (
            <div className="flex flex-col items-center py-4 border-r border-slate-200">
              <button
                onClick={() => setSidebarCollapsed(false)}
                className="p-2 rounded-lg hover:bg-slate-100 text-slate-600"
                title="Expand conversations list"
              >
                <ChevronRightIcon className="w-5 h-5" />
              </button>
            </div>
          ) : (
            <>
          <div className="flex justify-end pr-2 pt-2">
            <button
              onClick={() => setSidebarCollapsed(true)}
              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500"
              title="Collapse sidebar"
            >
              <ChevronLeftIcon className="w-4 h-4" />
            </button>
          </div>
          {/* 1) With bot – header fixed above, list scrolls below */}
          <div className="whatsapp-sidebar-section flex-1 flex flex-col min-h-0 bg-white overflow-hidden">
            {/* Header - fixed at top, never scrolls */}
            <div className="flex-shrink-0 pt-2 pb-3 bg-white border-b border-slate-100">
              <div className="flex items-center justify-between mb-3">
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
                <span className="text-xs text-slate-500 flex items-center space-x-1">
                  <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                  <span>Auto-updating</span>
                </span>
                {isLoading && (
                  <span className="text-xs text-slate-400">Loading...</span>
                )}
              </div>
              <div className="relative">
                <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  value={liveSearchQuery}
                  onChange={(e) => setLiveSearchQuery(e.target.value)}
                  placeholder="Search by name or phone..."
                  className="whatsapp-input w-full pl-9 pr-4"
                />
                {liveSearchQuery && (
                  <button
                    onClick={() => setLiveSearchQuery("")}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    <XMarkIcon className="w-4 h-4" />
                  </button>
                )}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
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
              <p className="mt-1 text-[11px] text-slate-500">
                {templateSendFilterViewActive
                  ? "Dates filter when the template was logged as sent (UTC day). Clear template filter to use dates for last activity only."
                  : "Dates filter conversations by last activity. For template send log, pick template below and Apply."}
              </p>
              <div className="mt-2 space-y-1">
                <label className="text-[11px] font-medium text-slate-600">Filter by sent template (Smart Messaging log)</label>
                <select
                  value={templateSendFilterId}
                  onChange={(e) => setTemplateSendFilterId(e.target.value)}
                  className="whatsapp-input w-full px-3 py-1.5 text-xs"
                  disabled={templateSendFilterLoading}
                >
                  <option value="">— Select template —</option>
                  {Object.keys(messagingTemplates)
                    .sort()
                    .map((tid) => (
                      <option key={tid} value={tid}>
                        {(messagingTemplates[tid]?.name || tid).slice(0, 80)}
                      </option>
                    ))}
                </select>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={templateSendFilterLoading}
                    onClick={() => applyTemplateSendFilter()}
                    className="text-xs px-2 py-1 rounded border border-violet-200 bg-violet-50 hover:bg-violet-100 text-violet-800 disabled:opacity-50"
                  >
                    {templateSendFilterLoading ? "Loading…" : "Apply template filter"}
                  </button>
                  <button
                    type="button"
                    disabled={templateSendFilterLoading}
                    onClick={() => clearTemplateSendFilter()}
                    className="text-xs px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 text-slate-600"
                  >
                    Clear template filter
                  </button>
                </div>
                {templateSendFilterMeta && templateSendFilterViewActive && (
                  <p className="text-[11px] text-slate-500">
                    Log rows: {templateSendFilterMeta.log_entries_matched ?? "—"} · Distinct phones:{" "}
                    {templateSendFilterMeta.distinct_recipients ?? "—"} · Chats shown:{" "}
                    {templateSendFilterMeta.matched_chats ?? "—"} (scanned {templateSendFilterMeta.index_scanned ?? "—"} index rows)
                  </p>
                )}
              </div>
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const today = new Date().toISOString().slice(0, 10);
                    setBotDateFrom(today);
                    setBotDateTo(today);
                  }}
                  className="text-xs px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 text-slate-600"
                >
                  Today
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setBotDateFrom("");
                    setBotDateTo("");
                  }}
                  className="text-xs px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 text-slate-600"
                >
                  Clear
                </button>
                <button
                  type="button"
                  disabled={rebuildingIndex}
                  onClick={async () => {
                    setRebuildingIndex(true);
                    try {
                      const r = await rebuildLiveChatIndex();
                      if (r?.success) {
                        toast.success(`Index rebuilt (${r.written ?? "?"} conversations)`);
                        const refreshed = await getUnifiedChats("", 1, CHAT_LIST_PAGE_SIZE);
                        if (refreshed?.success && Array.isArray(refreshed.chats)) {
                          applyServerConversations(refreshed.chats);
                          setHasMoreChats(refreshed.has_more ?? false);
                          setNextCursor(refreshed.next_cursor ?? null);
                        }
                      } else {
                        toast.error(r?.error || "Rebuild failed");
                      }
                    } catch (e) {
                      toast.error(errorMessage(e) || "Rebuild failed");
                    } finally {
                      setRebuildingIndex(false);
                    }
                  }}
                  className="text-xs px-2 py-1 rounded border border-amber-200 hover:bg-amber-50 text-amber-700"
                  title="If chats don't show, rebuild index from Firestore"
                >
                  {rebuildingIndex ? "Rebuilding..." : "Rebuild index"}
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const r = await simulateWebhook("9613000000", "Hello");
                      if (r?.success) {
                        toast.success("Test message sent – check Live Chat in a few seconds");
                        setTimeout(async () => {
                          const refreshed = await getUnifiedChats("", 1, CHAT_LIST_PAGE_SIZE);
                          if (refreshed?.success && Array.isArray(refreshed.chats)) {
                            applyServerConversations(refreshed.chats);
                          }
                        }, 2000);
                      } else {
                        toast.error(r?.error || "Simulate failed");
                      }
                    } catch (e) {
                      toast.error(errorMessage(e) || "Simulate failed");
                    }
                  }}
                  className="text-xs px-2 py-1 rounded border border-green-200 hover:bg-green-50 text-green-700"
                  title="Test if message flow works (simulates webhook)"
                >
                  Test flow
                </button>
                {isBotDateFilterActive && !templateSendFilterViewActive && (
                  <span className="text-[11px] text-slate-500">
                    Showing selected range (last activity)
                  </span>
                )}
              </div>
            </div>
            {/* List - scrolls independently below header */}
            <div
              className="flex-1 overflow-y-auto overflow-x-hidden min-h-0 py-3"
              ref={botListRef}
              onScroll={handleBotListScroll}
            >
            <div className="space-y-2">
              {isLoading && botConversations.length === 0 ? (
                [...Array(5)].map((_, i) => (
                  <div key={i} className="p-3 rounded-lg bg-slate-50 border border-slate-100 animate-pulse">
                    <div className="h-4 w-3/4 bg-slate-200 rounded mb-2" />
                    <div className="h-3 w-1/2 bg-slate-100 rounded mb-2" />
                    <div className="h-3 w-full bg-slate-100 rounded" />
                  </div>
                ))
              ) : (
                <>
                  {liveBotConversations.length > 0 && (
                    <div className="pt-1">
                      <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">Live now</p>
                      <div className="space-y-2">
                        {liveBotConversations.map((conv) => (
                          <div
                            key={`${conv.user_id}_${conv.conversation_id}`}
                            className={`p-3 rounded-lg cursor-pointer transition-all ${
                              selectedConversation?.conversation?.conversation_id ===
                              conv.conversation_id
                                ? "bg-primary-50 border-2 border-primary-300"
                                : "bg-slate-50 border border-slate-200 hover:bg-slate-100"
                            }`}
                            onClick={() => selectConversation(conv)}
                          >
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex-1">
                                <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                                  <p className="font-medium text-slate-800 text-sm">
                                    {conv.user_name}
                                  </p>
                                  <span className="inline-block px-2 py-0.5 bg-green-500 text-white text-xs font-bold rounded-full">
                                    Live
                                  </span>
                                  <NewCustomerBadge isNew={conv.is_new_customer} />
                                  {newConversationIds.has(conv.conversation_id) && (
                                    <span className="inline-block px-2 py-0.5 bg-blue-500 text-white text-xs font-bold rounded-full animate-pulse">
                                      New
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-slate-500">
                                  {formatPhoneForDisplay(conv.user_phone || conv.phone_number || "")}
                                </p>
                              </div>
                              <SentimentIndicator sentiment={conv.sentiment} />
                            </div>
                            <div className="mb-2"><StatusBadge status={conv.status} /></div>
                            {(lastMessageContent(conv.last_message) ?? conv.last_message_text) && (
                              <p className="text-xs text-slate-600 truncate mb-1">
                                {lastMessageContent(conv.last_message) ?? conv.last_message_text ?? ""}
                              </p>
                            )}
                            <div className="flex items-center justify-between text-xs text-slate-500">
                              <span>{(conv.message_count ?? 0)} messages</span>
                              <span>
                                {(conv.duration_seconds || 0) > 0
                                  ? `${Math.floor((conv.duration_seconds ?? 0) / 60)}m • `
                                  : ""}
                                {formatConversationListDate(conv)}
                              </span>
                            </div>
                            {conv.template_send_logged_at && (
                              <p className="text-[10px] text-violet-600 mt-1">
                                Sent (logged):{" "}
                                {new Date(conv.template_send_logged_at).toLocaleString()}
                              </p>
                            )}
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
                              selectedConversation?.conversation?.conversation_id ===
                              conv.conversation_id
                                ? "bg-primary-50 border-2 border-primary-300"
                                : "bg-slate-50 border border-slate-200 hover:bg-slate-100"
                            }`}
                            onClick={() => selectConversation(conv)}
                          >
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex-1">
                                <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                                  <p className="font-medium text-slate-800 text-sm">
                                    {conv.user_name}
                                  </p>
                                  <NewCustomerBadge isNew={conv.is_new_customer} />
                                  {newConversationIds.has(conv.conversation_id) && (
                                    <span className="inline-block px-2 py-0.5 bg-blue-500 text-white text-xs font-bold rounded-full animate-pulse">
                                      New
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-slate-500">
                                  {formatPhoneForDisplay(conv.user_phone || conv.phone_number || "")}
                                </p>
                              </div>
                              <SentimentIndicator sentiment={conv.sentiment} />
                            </div>
                            <div className="mb-2"><StatusBadge status={conv.status} /></div>
                            {(lastMessageContent(conv.last_message) ?? conv.last_message_text) && (
                              <p className="text-xs text-slate-600 truncate mb-1">
                                {lastMessageContent(conv.last_message) ?? conv.last_message_text ?? ""}
                              </p>
                            )}
                            <div className="flex items-center justify-between text-xs text-slate-500">
                              <span>{(conv.message_count ?? 0)} messages</span>
                              <span>
                                {(conv.duration_seconds || 0) > 0
                                  ? `${Math.floor((conv.duration_seconds ?? 0) / 60)}m • `
                                  : ""}
                                {formatConversationListDate(conv)}
                              </span>
                            </div>
                            {conv.template_send_logged_at && (
                              <p className="text-[10px] text-violet-600 mt-1">
                                Sent (logged):{" "}
                                {new Date(conv.template_send_logged_at).toLocaleString()}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
              {hasMoreChats && !templateSendFilterViewActive && (
                <div className="mt-2">
                  <div ref={botLoadMoreSentinelRef} className="h-2 min-h-[8px]" aria-hidden="true" />
                  <button
                    onClick={loadMoreChats}
                    disabled={loadingMoreChats}
                    className="w-full py-3 text-sm font-medium text-primary-600 hover:bg-primary-50 rounded-lg border border-primary-200 transition disabled:opacity-60"
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
                </div>
              )}
            </div>
            </div>
          </div>
            </>
          )}
        </motion.div>

    </>
  );
}
