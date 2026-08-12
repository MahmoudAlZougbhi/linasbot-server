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

export function LiveChatModals(s) {
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
    <>
      {feedbackModal?.feedbackType === "like" && (
        <LikeFeedbackModal
          message={feedbackModal.message}
          userQuestion={getPreviousUserMessage(feedbackModal.message)}
          onClose={() => setFeedbackModal(null)}
          onSubmit={submitLikeToFaq}
        />
      )}
      {feedbackModal?.feedbackType === "wrong" && (
        <FeedbackModal
          message={feedbackModal.message}
          conversation={selectedConversation?.conversation}
          onClose={() => setFeedbackModal(null)}
          onSubmit={submitCorrection}
        />
      )}

      {editMessageModal?.message && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-2xl p-6 max-w-lg w-full mx-4 shadow-xl"
          >
            <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center">
              <span className="text-xl mr-2">✏️</span>
              Edit bot reply
            </h3>
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              placeholder="Edit the reply text..."
              className="input-field w-full min-h-[120px] resize-y mb-4"
              disabled={isSubmittingEdit}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditMessageModal(null)}
                className="btn-secondary"
                disabled={isSubmittingEdit}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={submitEditMessage}
                className="btn-primary disabled:opacity-50"
                disabled={isSubmittingEdit || !(editContent || "").trim()}
              >
                {isSubmittingEdit ? "Saving..." : "Save changes"}
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {faqCorrectionModal?.message && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-2xl p-6 max-w-lg w-full mx-4 shadow-xl max-h-[90vh] overflow-y-auto"
          >
            <h3 className="text-lg font-bold text-slate-800 mb-1 flex items-center">
              <span className="text-xl mr-2">📚</span>
              Correct reply from FAQ
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              View the original FAQ question that matched the user{"'"}s message, the match score, and edit the answer. Save Change = update the same question in all languages. Save New = save the user{"'"}s question with the answer as a new FAQ entry in all languages without changing the original.
            </p>
            {faqContextLoading ? (
              <p className="text-slate-500 text-sm">Loading match context...</p>
            ) : faqContext?.faq_match ? (
              <>
                <div className="space-y-3 mb-4 text-sm">
                  <div>
                    <span className="font-medium text-slate-600">Original FAQ question that matched the user{"'"}s message:</span>
                    <p className="mt-1 p-2 bg-slate-50 rounded border border-slate-200 text-slate-800">
                      {faqContext.faq_match.stored_question || "—"}
                    </p>
                  </div>
                  <div>
                    <span className="font-medium text-slate-600">User{"'"}s question:</span>
                    <p className="mt-1 p-2 bg-slate-50 rounded border border-slate-200 text-slate-800">
                      {faqContext.faq_match.user_question || "—"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-600">Match score:</span>
                    <span className="text-primary-600 font-medium">
                      {faqContext.faq_match.similarity != null
                        ? `${Math.round(Number(faqContext.faq_match.similarity) * 100)}%`
                        : "—"}
                    </span>
                    {faqContext.faq_match.tier && (
                      <span className="text-xs px-2 py-0.5 bg-slate-200 rounded">{faqContext.faq_match.tier}</span>
                    )}
                  </div>
                </div>
                <div className="mb-4">
                  <label className="block text-sm font-medium text-slate-700 mb-2">Answer (editable):</label>
                  <textarea
                    value={faqEditAnswer}
                    onChange={(e) => setFaqEditAnswer(e.target.value)}
                    placeholder="Edit the answer..."
                    className="input-field w-full min-h-[100px] resize-y"
                    disabled={faqSubmitting}
                  />
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setFaqCorrectionModal(null)}
                    className="btn-secondary"
                    disabled={faqSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleFaqSaveChange}
                    className="btn-primary disabled:opacity-50"
                    disabled={faqSubmitting || !(faqEditAnswer || "").trim()}
                  >
                    {faqSubmitting ? "..." : "Save Change — Update original question answer in all languages"}
                  </button>
                  <button
                    type="button"
                    onClick={handleFaqSaveNew}
                    className="bg-slate-600 hover:bg-slate-700 text-white px-4 py-2 rounded-lg disabled:opacity-50"
                    disabled={faqSubmitting || !(faqEditAnswer || "").trim()}
                  >
                    {faqSubmitting
                      ? "..."
                      : "Save New — Save user\u2019s question + answer as new FAQ in all languages (original unchanged)"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="space-y-3 mb-4 text-sm">
                  <div>
                    <span className="font-medium text-slate-600">Original FAQ question:</span>
                    <p className="mt-1 p-2 bg-slate-100 rounded border border-slate-200 text-slate-500 italic">—</p>
                  </div>
                  <div>
                    <span className="font-medium text-slate-600">User{"'"}s question:</span>
                    <p className="mt-1 p-2 bg-slate-50 rounded border border-slate-200 text-slate-800">
                      {getPreviousUserMessage(faqCorrectionModal.message) || "—"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-600">Match score:</span>
                    <span className="text-slate-400">—</span>
                  </div>
                </div>
                <div className="mb-4">
                  <label className="block text-sm font-medium text-slate-700 mb-2">Answer (editable):</label>
                  <textarea
                    value={faqEditAnswer}
                    onChange={(e) => setFaqEditAnswer(e.target.value)}
                    placeholder="Edit the answer..."
                    className="input-field w-full min-h-[100px] resize-y"
                    disabled={faqSubmitting}
                  />
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setFaqCorrectionModal(null)}
                    className="btn-secondary"
                    disabled={faqSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleFaqSaveNew}
                    className="bg-slate-600 hover:bg-slate-700 text-white px-4 py-2 rounded-lg disabled:opacity-50"
                    disabled={faqSubmitting || !(faqEditAnswer || "").trim()}
                  >
                    {faqSubmitting ? "..." : "Save New — Save user's question + answer as new FAQ in all languages"}
                  </button>
                </div>
              </>
            )}
          </motion.div>
        </div>
      )}
    </>
  );

    </>
  );
}
