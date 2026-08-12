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

export function LiveChatThreadMessages(s) {
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
              {/* Messages - Fixed Height with Internal Scroll */}
              <div
                ref={messagesContainerRef}
                className="whatsapp-chat-bg flex-1 overflow-y-auto p-4 space-y-3 min-h-0 flex flex-col"
              >
                {hasMoreMessages && (
                  <button
                    onClick={loadMoreMessages}
                    disabled={loadingMoreMessages}
                    className="self-center py-2 px-4 text-sm text-primary-600 hover:bg-primary-50 rounded-lg border border-primary-200 mb-2"
                  >
                    {loadingMoreMessages ? "Loading..." : "Load More (older)"}
                  </button>
                )}
                {/* ✅ Loading indicator for messages */}
                {messagesLoading && (selectedConversation.history || []).length === 0 && (
                  <div className="flex items-center justify-center h-full">
                    <div className="text-center">
                      <svg
                        className="animate-spin h-8 w-8 mx-auto mb-3 text-primary-500"
                        xmlns="http://www.w3.org/2000/svg"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                        ></circle>
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        ></path>
                      </svg>
                      <p className="text-slate-500 text-sm">Loading messages...</p>
                    </div>
                  </div>
                )}
                {!messagesLoading && (selectedConversation.history || []).length === 0 && (
                  <div className="flex flex-col items-center justify-center h-full min-h-[200px] text-slate-500">
                    <p className="text-sm mb-3">No messages loaded</p>
                    <button
                      type="button"
                      onClick={reloadSelectedConversationMessages}
                      className="px-4 py-2 text-sm font-medium text-primary-600 bg-primary-50 rounded-lg border border-primary-200 hover:bg-primary-100"
                    >
                      Reload messages
                    </button>
                  </div>
                )}
                {(selectedConversation.history || []).map((msg, index) => {
                  const messageText = msg.content || msg.text || "";
                  // ✅ Check if this is a voice message - Updated to use new Firebase structure
                  // First check msg.type (preferred), fallback to old content-based detection
                  const isVoiceMessage =
                    msg.type === "voice" ||
                    messageText === "[رسالة صوتية]" ||
                    messageText === "رسالة صوتية" ||
                    msg.audio_url;

                  // ✅ Check if this is an image message - Use new Firebase structure
                  const isImageMessage =
                    msg.type === "image" ||
                    messageText === "[صورة]" ||
                    msg.image_url;

                  return (
                    <div
                      key={
                        msg.message_id ||
                        msg.id ||
                        `${msg.timestamp || "no-ts"}-${msg.type || "text"}-${msg.is_user ? "u" : "a"}-${String(
                          msg.audio_url || msg.image_url || msg.text || msg.content || ""
                        ).slice(0, 60)}-${index}`
                      }
                      className={`flex ${
                        msg.is_user ? "justify-start" : "justify-end"
                      }`}
                    >
                      <div
                        className={`max-w-[70%] ${
                          msg.is_user ? "order-2" : "order-1"
                        }`}
                      >
                        <div
                          className={`px-4 py-2 ${
                            msg.is_user
                              ? "whatsapp-message-in"
                              : "whatsapp-message-out"
                          }`}
                        >
                          {isImageMessage ? (
                            <div className="flex flex-col space-y-2">
                              {msg.image_url ? (
                                <div className="max-w-xs">
                                  <img
                                    src={msg.image_url}
                                    alt="Attachment"
                                    className="rounded-lg max-w-full h-auto object-cover"
                                    onError={(e) => {
                                      const img = /** @type {HTMLImageElement} */ (e.currentTarget);
                                      img.src =
                                        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect fill='%23e5e7eb' width='100' height='100'/%3E%3Ctext x='50' y='50' text-anchor='middle' dy='.3em' fill='%23999' font-size='12'%3EImage unavailable%3C/text%3E%3C/svg%3E";
                                    }}
                                  />
                                </div>
                              ) : (
                                <div className="flex items-center space-x-2">
                                  <span className="text-sm">Image</span>
                                  <span className="text-xs opacity-75">
                                    (Link unavailable)
                                  </span>
                                </div>
                              )}
                            </div>
                          ) : isVoiceMessage ? (
                            <div className="flex items-start space-x-3">
                              <div className="flex-shrink-0">
                                <svg
                                  className="w-8 h-8"
                                  fill="currentColor"
                                  viewBox="0 0 20 20"
                                >
                                  <path
                                    fillRule="evenodd"
                                    d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 00-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z"
                                    clipRule="evenodd"
                                  />
                                </svg>
                              </div>
                              <div className="flex-1">
                                {msg.audio_url ? (
                                  <div>
                                    {/* ✅ Modern WhatsApp-style audio player */}
                                    <ModernAudioPlayer
                                      audioUrl={msg.audio_url}
                                      isUserMessage={msg.is_user}
                                    />
                                    {/* ✅ Show transcribed text below audio player */}
                                    {msg.text &&
                                      msg.text !== "[رسالة صوتية]" &&
                                      msg.text !== "رسالة صوتية" && (
                                        <p className="text-xs mt-2 opacity-90">
                                          {msg.text}
                                        </p>
                                      )}
                                  </div>
                                ) : (
                                  <div className="flex items-center space-x-2">
                                    <span className="text-sm">Voice message</span>
                                    <span className="text-xs opacity-75">
                                      (URL not available)
                                    </span>
                                  </div>
                                )}
                              </div>
                            </div>
                          ) : (
                            <p className="text-sm">{messageText}</p>
                          )}
                        </div>
                        <div className="flex items-center space-x-2 mt-1 px-2">
                          <span className="text-xs text-slate-400">
                            {formatMessageTime(msg.timestamp || "")}
                          </span>
                          {!msg.is_user && msg.handled_by && (
                            <>
                              <span className="text-xs text-slate-500">
                                •{" "}
                                {msg.handled_by === "ai"
                                  ? "✨ AI"
                                  : msg.handled_by === "bot"
                                  ? "🤖 Bot"
                                  : "👤 Human"}
                              </span>
                              {msg.handled_by === "ai" &&
                                !isVoiceMessage &&
                                !isImageMessage && (
                                  <button
                                    onClick={() =>
                                      handleFeedback(msg, "like")
                                    }
                                    className="text-xs hover:scale-125 transition-transform ml-2"
                                    title="Save to FAQ (edit & save in 4 languages)"
                                  >
                                    👍
                                  </button>
                                )}
                              {msg.handled_by === "bot" &&
                                !isVoiceMessage &&
                                !isImageMessage && (
                                  <button
                                    onClick={() =>
                                      handleFeedback(msg, "wrong")
                                    }
                                    className="text-xs hover:scale-125 transition-transform ml-2"
                                    title="Dislike — Correct or edit the reply"
                                  >
                                    👎
                                  </button>
                                )}
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
                <div ref={messagesEndRef} />
              </div>

              {/* Message Input - Fixed Height - Text + Voice */}
              {selectedConversation.conversation.status === "human" && (
                <div className="whatsapp-input-bar flex-shrink-0">
                  {selectedImage && (
                    <div className="mb-3 p-3 bg-slate-100 rounded-lg">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-3 min-w-0">
                          <img
                            src={typeof selectedImage.preview === "string" ? selectedImage.preview : undefined}
                            alt={selectedImage.name || "Selected image"}
                            className="w-12 h-12 rounded object-cover"
                          />
                          <p className="text-sm text-slate-700 truncate">
                            {selectedImage.name || "Image selected"}
                          </p>
                        </div>
                        <div className="flex items-center space-x-2">
                          <button
                            onClick={discardImage}
                            className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                            title="Discard image"
                          >
                            <XMarkIcon className="w-5 h-5" />
                          </button>
                          <button
                            onClick={sendImageMessage}
                            className="whatsapp-pill flex items-center space-x-1"
                          >
                            <PaperAirplaneIcon className="w-4 h-4" />
                            <span>Send</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Voice Recording Preview */}
                  {recordedAudio && (
                    <div className="mb-3 p-3 bg-slate-100 rounded-lg">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                          <MicrophoneIcon className="w-5 h-5 text-primary-600" />
                          <audio
                            src={recordedAudio.url}
                            controls
                            className="h-8"
                          />
                        </div>
                        <div className="flex items-center space-x-2">
                          <button
                            onClick={discardRecording}
                            className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                            title="Discard recording"
                          >
                            <XMarkIcon className="w-5 h-5" />
                          </button>
                          <button
                            onClick={sendVoiceMessage}
                            disabled={isSendingVoice}
                            className="whatsapp-pill flex items-center space-x-1 disabled:opacity-50"
                          >
                            <PaperAirplaneIcon className="w-4 h-4" />
                            <span>{isSendingVoice ? "Sending..." : "Send"}</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Recording in Progress */}
                  {isRecording && (
                    <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                          <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
                          <span className="text-red-700 font-medium">
                            Recording... {formatRecordingTime(recordingTime)}
                          </span>
                        </div>
                        <button
                          onClick={stopRecording}
                          className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors flex items-center space-x-2"
                        >
                          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                            <rect x="6" y="6" width="8" height="8" rx="1" />
                          </svg>
                          <span>Stop</span>
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Text Message Input with Voice Button */}
                  {!isRecording && !recordedAudio && (
                    <div className="flex space-x-2">
                      <input
                        ref={imageInputRef}
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={handleImageSelect}
                      />
                      <input
                        type="text"
                        value={messageInput}
                        onChange={(e) => setMessageInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key !== "Enter" || e.shiftKey) return;
                          e.preventDefault();
                          if (isSending || sendingRef.current) return;
                          handleSendMessage();
                        }}
                        placeholder="Type your message..."
                        className="whatsapp-input flex-1"
                        disabled={isSending}
                      />
                      {/* Voice Recording Button */}
                      <button
                        onClick={startRecording}
                        className="whatsapp-action-btn"
                        title="Record voice message"
                      >
                        <MicrophoneIcon className="w-5 h-5" />
                      </button>
                      <button
                        onClick={() => imageInputRef.current?.click()}
                        className="whatsapp-action-btn"
                        title="Send image"
                      >
                        <PhotoIcon className="w-5 h-5" />
                      </button>
                      {/* Send Text Button */}
                      <button
                        onClick={handleSendMessage}
                        disabled={isSending || !messageInput.trim()}
                        className="whatsapp-send-btn"
                      >
                        {isSending ? (
                          <span className="flex items-center">
                            <svg
                              className="animate-spin -ml-1 mr-2 h-5 w-5"
                              xmlns="http://www.w3.org/2000/svg"
                              fill="none"
                              viewBox="0 0 24 24"
                            >
                              <circle
                                className="opacity-25"
                                cx="12"
                                cy="12"
                                r="10"
                                stroke="currentColor"
                                strokeWidth="4"
                              ></circle>
                              <path
                                className="opacity-75"
                                fill="currentColor"
                                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                              ></path>
                            </svg>
                            Sending...
                          </span>
                        ) : (
                          <PaperAirplaneIcon className="w-5 h-5" />
                        )}
                      </button>
                    </div>
                  )}
                </div>
              )}

    </>
  );
}
