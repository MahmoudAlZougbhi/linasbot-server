import {
  ArrowRightIcon,
  ChartBarIcon,
  ChevronLeftIcon,
  MagnifyingGlassIcon,
  MicrophoneIcon,
  PaperAirplaneIcon,
  PhotoIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import ModernAudioPlayer from "./ModernAudioPlayer";
import {
  NewCustomerBadge,
  SentimentIndicator,
  StatusBadge,
} from "./ConversationIndicators";
import { formatMessageTime } from "../../utils/dateUtils";

/** @param {LiveChatMessage | string | null | undefined} lastMessage */
const previewLastMessage = (lastMessage) => {
  if (!lastMessage) return "";
  if (typeof lastMessage === "string") return lastMessage;
  return String(lastMessage.content || lastMessage.text || "");
};

/**
 * @param {{
 *   formatLastRefreshTime: () => string;
 *   handleManualRefresh: () => void;
 *   isRefreshing: boolean;
 *   setMobileFilterSheetOpen: (open: boolean) => void;
 *   liveSearchQuery: string;
 *   setLiveSearchQuery: (value: string) => void;
 *   mobileListSection: string;
 *   setMobileListSection: (section: string) => void;
 *   filteredWaitingQueue: QueueItem[];
 *   filteredWithOperator: LiveChatConversation[];
 *   filteredBotConversations: LiveChatConversation[];
 *   mobileVisibleConversations: Array<QueueItem | LiveChatConversation>;
 *   isLoading: boolean;
 *   buildConversationFromQueueItem: (entry: QueueItem) => LiveChatConversation;
 *   getConversationUnreadCount: (entry: QueueItem | LiveChatConversation) => number;
 *   formatPhoneForDisplay: (phone: string | undefined) => string;
 *   formatConversationListDate: (conv: LiveChatConversation) => string;
 *   openWaitingConversation: (entry: QueueItem) => void;
 *   openConversation: (conv: LiveChatConversation) => void;
 *   mobileFilterSheetOpen: boolean;
 *   botDateFrom: string;
 *   setBotDateFrom: (value: string) => void;
 *   botDateTo: string;
 *   setBotDateTo: (value: string) => void;
 *   hasMoreChats: boolean;
 *   loadingMoreChats: boolean;
 *   loadMoreChats: () => void;
 *   selectedConversation: SelectedConversation | null;
 *   setSelectedConversation: import('react').Dispatch<import('react').SetStateAction<SelectedConversation | null>>;
 *   reloadSelectedConversationMessages: () => void;
 *   messagesContainerRef: import('react').RefObject<HTMLDivElement>;
 *   messagesLoading: boolean;
 *   messagesEndRef: import('react').RefObject<HTMLDivElement>;
 *   handleFeedback: (message: LiveChatMessage, type: string) => void;
 *   mobileDetailsOpen: boolean;
 *   setMobileDetailsOpen: (open: boolean) => void;
 *   handleTakeOver: (conversationId: string, userId: string) => void;
 *   handleReleaseToBot: (conversationId: string, userId: string) => void;
 *   handleEndConversation: (conversationId: string, userId: string) => void;
 *   selectedImage: { file: File; preview: string | ArrayBuffer | null; name: string } | null;
 *   discardImage: () => void;
 *   sendImageMessage: () => void;
 *   recordedAudio: { blob: Blob; url: string } | null;
 *   discardRecording: () => void;
 *   sendVoiceMessage: () => void;
 *   isSendingVoice: boolean;
 *   imageInputRef: import('react').RefObject<HTMLInputElement>;
 *   handleImageSelect: (event: import('react').ChangeEvent<HTMLInputElement>) => void;
 *   isRecording: boolean;
 *   recordingTime: number;
 *   stopRecording: () => void;
 *   startRecording: () => void;
 *   formatRecordingTime: (seconds: number) => string;
 *   messageInput: string;
 *   setMessageInput: (value: string) => void;
 *   handleSendMessage: () => void;
 *   isSending: boolean;
 * }} props
 */
const MobileLiveChatView = ({
  formatLastRefreshTime,
  handleManualRefresh,
  isRefreshing,
  setMobileFilterSheetOpen,
  liveSearchQuery,
  setLiveSearchQuery,
  mobileListSection,
  setMobileListSection,
  filteredWaitingQueue,
  filteredWithOperator,
  filteredBotConversations,
  mobileVisibleConversations,
  isLoading,
  buildConversationFromQueueItem,
  getConversationUnreadCount,
  formatPhoneForDisplay,
  formatConversationListDate,
  openWaitingConversation,
  openConversation,
  mobileFilterSheetOpen,
  botDateFrom,
  setBotDateFrom,
  botDateTo,
  setBotDateTo,
  hasMoreChats,
  loadingMoreChats,
  loadMoreChats,
  selectedConversation,
  setSelectedConversation,
  reloadSelectedConversationMessages,
  messagesContainerRef,
  messagesLoading,
  messagesEndRef,
  handleFeedback,
  mobileDetailsOpen,
  setMobileDetailsOpen,
  handleTakeOver,
  handleReleaseToBot,
  handleEndConversation,
  selectedImage,
  discardImage,
  sendImageMessage,
  recordedAudio,
  discardRecording,
  sendVoiceMessage,
  isSendingVoice,
  imageInputRef,
  handleImageSelect,
  isRecording,
  recordingTime,
  stopRecording,
  startRecording,
  formatRecordingTime,
  messageInput,
  setMessageInput,
  handleSendMessage,
  isSending,
}) => {
  const currentConversation = selectedConversation?.conversation;
  const currentHistory = selectedConversation?.history || [];
  const currentStatus = currentConversation?.status;

  return (
    <div className="h-[100dvh] bg-slate-950 text-slate-100 flex flex-col overflow-hidden">
      {!currentConversation ? (
        <>
          <div className="px-4 mobile-safe-top pb-3 border-b border-white/10 bg-slate-950/95 backdrop-blur flex-shrink-0">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h1 className="text-lg font-semibold">Live Chat</h1>
                <p className="text-xs text-slate-400">{formatLastRefreshTime()}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setMobileFilterSheetOpen(true)}
                  className="p-2 rounded-full bg-white/5 border border-white/10"
                >
                  <ChartBarIcon className="w-5 h-5" />
                </button>
                <button
                  onClick={handleManualRefresh}
                  disabled={isRefreshing}
                  className="p-2 rounded-full bg-emerald-500 text-white disabled:opacity-50"
                >
                  <ArrowRightIcon
                    className={`w-4 h-4 ${isRefreshing ? "animate-spin" : "rotate-[-45deg]"}`}
                  />
                </button>
              </div>
            </div>

            <div className="relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={liveSearchQuery}
                onChange={(e) => setLiveSearchQuery(e.target.value)}
                placeholder="Search by name or phone..."
                className="w-full rounded-2xl bg-white/5 border border-white/10 pl-10 pr-10 py-3 text-sm text-white placeholder:text-slate-500 outline-none"
              />
              {liveSearchQuery && (
                <button
                  onClick={() => setLiveSearchQuery("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
                >
                  <XMarkIcon className="w-4 h-4" />
                </button>
              )}
            </div>

            <div className="grid grid-cols-3 gap-2 mt-3">
              {[
                { key: "queue", label: `Queue (${filteredWaitingQueue.length})` },
                { key: "mine", label: `Mine (${filteredWithOperator.length})` },
                { key: "bot", label: `Bot (${filteredBotConversations.length})` },
              ].map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setMobileListSection(tab.key)}
                  className={`rounded-2xl px-3 py-2 text-xs font-medium transition ${
                    mobileListSection === tab.key
                      ? "bg-emerald-500 text-white"
                      : "bg-white/5 text-slate-300 border border-white/10"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
            {isLoading && mobileVisibleConversations.length === 0 ? (
              <div className="p-4 rounded-3xl bg-white/5 border border-white/10 text-center text-sm text-slate-400">
                Loading conversations...
              </div>
            ) : mobileVisibleConversations.length === 0 ? (
              <div className="p-6 rounded-3xl bg-white/5 border border-white/10 text-center text-sm text-slate-400">
                No conversations in this section.
              </div>
            ) : (
              mobileVisibleConversations.map((/** @type {QueueItem | LiveChatConversation} */ entry) => {
                const isQueueItem = mobileListSection === "queue";
                /** @type {LiveChatConversation} */
                const conv = isQueueItem
                  ? buildConversationFromQueueItem(/** @type {QueueItem} */ (entry))
                  : /** @type {LiveChatConversation} */ (entry);
                const unreadCount = getConversationUnreadCount(isQueueItem ? conv : entry);
                const lastPreview = previewLastMessage(conv.last_message || (isQueueItem ? entry.last_message : null)).trim();
                const queueEntry = /** @type {QueueItem} */ (entry);

                return (
                  <button
                    key={`${conv.user_id}_${conv.conversation_id}`}
                    onClick={() =>
                      isQueueItem ? openWaitingConversation(entry) : openConversation(conv)
                    }
                    className="w-full text-left rounded-3xl p-4 bg-white text-slate-900 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="font-semibold truncate">{String(conv.user_name || conv.user_id)}</p>
                          <NewCustomerBadge isNew={Boolean(conv.is_new_customer)} />
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <StatusBadge status={String(conv.status || "bot")} />
                          {!isQueueItem && <SentimentIndicator sentiment={String(conv.sentiment || "neutral")} />}
                        </div>
                        <p className="text-xs text-slate-500 mt-2 truncate">
                          {lastPreview ||
                            formatPhoneForDisplay(conv.user_phone || conv.phone_number || "") ||
                            "Open conversation"}
                        </p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <p className="text-[11px] text-slate-500">
                          {isQueueItem
                            ? `${Math.floor((Number(queueEntry.wait_time_seconds) || 0) / 60)}m`
                            : formatConversationListDate(conv)}
                        </p>
                        {unreadCount > 0 && (
                          <span className="mt-2 inline-flex min-w-[22px] h-[22px] items-center justify-center rounded-full bg-emerald-600 px-1 text-[11px] font-bold text-white">
                            {unreadCount}
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })
            )}

            {mobileListSection === "bot" && hasMoreChats && (
              <button
                onClick={loadMoreChats}
                disabled={loadingMoreChats}
                className="w-full rounded-2xl px-4 py-3 bg-white/5 text-slate-200 border border-white/10 disabled:opacity-50"
              >
                {loadingMoreChats ? "Loading..." : "Load more conversations"}
              </button>
            )}
          </div>

          {mobileFilterSheetOpen && (
            <div
              className="fixed inset-0 z-40 bg-black/40"
              onClick={() => setMobileFilterSheetOpen(false)}
            >
              <div
                className="absolute inset-x-0 bottom-0 rounded-t-3xl bg-white p-4 text-slate-900 shadow-2xl"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="w-12 h-1.5 rounded-full bg-slate-300 mx-auto mb-4" />
                <h3 className="font-semibold text-base mb-3">Mobile filters</h3>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-slate-500 block mb-1">
                      Bot date from
                    </label>
                    <input
                      type="date"
                      value={botDateFrom}
                      onChange={(e) => setBotDateFrom(e.target.value)}
                      className="input-field w-full"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-slate-500 block mb-1">
                      Bot date to
                    </label>
                    <input
                      type="date"
                      value={botDateTo}
                      onChange={(e) => setBotDateTo(e.target.value)}
                      className="input-field w-full"
                    />
                  </div>
                  <button
                    onClick={() => {
                      setBotDateFrom("");
                      setBotDateTo("");
                      setMobileFilterSheetOpen(false);
                    }}
                    className="w-full btn-ghost"
                  >
                    Clear filters
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="px-3 mobile-safe-top pb-2 border-b border-white/10 bg-slate-950/95 backdrop-blur flex items-center gap-3 flex-shrink-0">
            <button
              onClick={() => {
                setMobileDetailsOpen(false);
                setSelectedConversation(null);
              }}
              className="p-2 rounded-full bg-white/5 border border-white/10"
            >
              <ChevronLeftIcon className="w-5 h-5" />
            </button>
            <button
              onClick={() => setMobileDetailsOpen(true)}
              className="min-w-0 flex-1 text-left"
            >
              <div className="flex items-center gap-2">
                <p className="font-semibold truncate">{String(currentConversation.user_name || currentConversation.user_id)}</p>
                <NewCustomerBadge isNew={Boolean(currentConversation.is_new_customer)} />
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-400 mt-0.5">
                <StatusBadge status={String(currentConversation.status || "bot")} />
                <span>
                  {formatPhoneForDisplay(
                    currentConversation.user_phone || currentConversation.phone_number || ""
                  )}
                </span>
              </div>
            </button>
            <button
              onClick={reloadSelectedConversationMessages}
              className="p-2 rounded-full bg-white/5 border border-white/10"
            >
              <ArrowRightIcon className="w-4 h-4 rotate-[-45deg]" />
            </button>
          </div>

          <div
            ref={messagesContainerRef}
            className="flex-1 overflow-y-auto px-3 py-4 space-y-3 bg-[#0b141a]"
          >
            {messagesLoading && currentHistory.length === 0 && (
              <div className="text-center text-sm text-slate-400">Loading messages...</div>
            )}
            {!messagesLoading && currentHistory.length === 0 && (
              <div className="text-center text-sm text-slate-400">
                <p>No messages loaded</p>
                <button
                  type="button"
                  onClick={reloadSelectedConversationMessages}
                  className="mt-3 px-4 py-2 text-sm font-medium text-emerald-300 bg-emerald-500/10 rounded-xl border border-emerald-400/20"
                >
                  Reload messages
                </button>
              </div>
            )}

            {currentHistory.map((/** @type {LiveChatMessage} */ msg, /** @type {number} */ index) => {
              const messageText = msg.content || msg.text || "";
              const isVoiceMessage =
                msg.type === "voice" ||
                messageText === "[رسالة صوتية]" ||
                messageText === "رسالة صوتية" ||
                msg.audio_url;
              const isImageMessage =
                msg.type === "image" ||
                messageText === "[صورة]" ||
                msg.image_url;

              return (
                <div
                  key={
                    msg.message_id ||
                    msg.id ||
                    `${msg.timestamp || "no-ts"}-${msg.type || "text"}-${msg.is_user ? "u" : "a"}-${index}`
                  }
                  className={`flex ${msg.is_user ? "justify-start" : "justify-end"}`}
                >
                  <div className={`max-w-[85%] ${msg.is_user ? "order-2" : "order-1"}`}>
                    <div
                      className={`px-4 py-2.5 ${
                        msg.is_user ? "whatsapp-message-in" : "whatsapp-message-out"
                      }`}
                    >
                      {isImageMessage ? (
                        msg.image_url ? (
                          <img
                            src={String(msg.image_url)}
                            alt="Attachment"
                            className="rounded-xl max-w-full h-auto object-cover"
                          />
                        ) : (
                          <p className="text-sm">Image unavailable</p>
                        )
                      ) : isVoiceMessage ? (
                        <div className="flex flex-col gap-2">
                          {msg.audio_url ? (
                            <ModernAudioPlayer
                              audioUrl={String(msg.audio_url)}
                              isUserMessage={Boolean(msg.is_user)}
                            />
                          ) : (
                            <p className="text-sm">Voice message</p>
                          )}
                          {msg.text &&
                            msg.text !== "[رسالة صوتية]" &&
                            msg.text !== "رسالة صوتية" && (
                              <p className="text-xs opacity-90">{msg.text}</p>
                            )}
                        </div>
                      ) : (
                        <p className="text-sm whitespace-pre-wrap break-words">{messageText}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1 px-2">
                      <span className="text-[11px] text-slate-400">
                        {formatMessageTime(String(msg.timestamp || ""))}
                      </span>
                      {!msg.is_user && msg.handled_by != null && (
                        <>
                          <span className="text-[11px] text-slate-500">
                            {msg.handled_by === "ai"
                              ? "AI"
                              : msg.handled_by === "bot"
                              ? "Bot"
                              : "Human"}
                          </span>
                          {msg.handled_by === "ai" &&
                            !isVoiceMessage &&
                            !isImageMessage && (
                              <button
                                onClick={() => handleFeedback(msg, "like")}
                                className="text-xs hover:scale-110 transition-transform"
                                title="Save to FAQ"
                              >
                                👍
                              </button>
                            )}
                          {msg.handled_by === "bot" &&
                            !isVoiceMessage &&
                            !isImageMessage && (
                              <button
                                onClick={() => handleFeedback(msg, "wrong")}
                                className="text-xs hover:scale-110 transition-transform"
                                title="Correct reply"
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

          {currentStatus === "human" ? (
            <div className="px-3 pt-2 mobile-safe-bottom bg-slate-950 border-t border-white/10 flex-shrink-0">
              {selectedImage && (
                <div className="mb-3 p-3 bg-white/5 rounded-2xl border border-white/10">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <img
                        src={typeof selectedImage.preview === "string" ? selectedImage.preview : ""}
                        alt={selectedImage.name || "Selected image"}
                        className="w-12 h-12 rounded-xl object-cover"
                      />
                      <p className="text-sm text-slate-200 truncate">
                        {selectedImage.name || "Image selected"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={discardImage}
                        className="p-2 text-red-300 rounded-full bg-red-500/10"
                      >
                        <XMarkIcon className="w-5 h-5" />
                      </button>
                      <button
                        onClick={sendImageMessage}
                        className="whatsapp-pill flex items-center gap-1"
                      >
                        <PaperAirplaneIcon className="w-4 h-4" />
                        <span>Send</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {recordedAudio && (
                <div className="mb-3 p-3 bg-white/5 rounded-2xl border border-white/10">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <MicrophoneIcon className="w-5 h-5 text-emerald-300" />
                      <audio src={recordedAudio.url} controls className="h-8 max-w-[180px]" />
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={discardRecording}
                        className="p-2 text-red-300 rounded-full bg-red-500/10"
                      >
                        <XMarkIcon className="w-5 h-5" />
                      </button>
                      <button
                        onClick={sendVoiceMessage}
                        disabled={isSendingVoice}
                        className="whatsapp-pill flex items-center gap-1 disabled:opacity-50"
                      >
                        <PaperAirplaneIcon className="w-4 h-4" />
                        <span>Send</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex items-end gap-2">
                <button
                  onClick={() => imageInputRef.current?.click()}
                  className="p-3 rounded-full bg-white/5 border border-white/10 text-slate-200"
                >
                  <PhotoIcon className="w-5 h-5" />
                </button>
                <button
                  onClick={isRecording ? stopRecording : startRecording}
                  className={`p-3 rounded-full border ${
                    isRecording
                      ? "bg-red-500 text-white border-red-400"
                      : "bg-white/5 text-slate-200 border-white/10"
                  }`}
                >
                  <MicrophoneIcon className="w-5 h-5" />
                </button>
                <input
                  ref={imageInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleImageSelect}
                />
                <div className="flex-1 rounded-[28px] bg-white/5 border border-white/10 px-4 py-2">
                  <textarea
                    value={messageInput}
                    onChange={(e) => setMessageInput(e.target.value)}
                    placeholder={
                      isRecording
                        ? `Recording... ${formatRecordingTime(recordingTime)}`
                        : "Type a message"
                    }
                    className="w-full bg-transparent resize-none outline-none text-sm text-white placeholder:text-slate-500 min-h-[24px] max-h-28"
                    rows={1}
                  />
                </div>
                <button
                  onClick={handleSendMessage}
                  disabled={!messageInput.trim() || isSending}
                  className="whatsapp-send-btn disabled:opacity-50"
                >
                  <PaperAirplaneIcon className="w-5 h-5" />
                </button>
              </div>
            </div>
          ) : (
            <div className="px-3 py-3 mobile-safe-bottom bg-slate-950 border-t border-white/10">
              <div className="rounded-2xl bg-white/5 border border-white/10 p-3">
                <p className="text-sm text-slate-300 mb-3">
                  {currentStatus === "human"
                    ? "Human operator is handling this conversation."
                    : "Take over this conversation to reply as an operator."}
                </p>
                {currentStatus !== "human" && (
                  <button
                    onClick={() =>
                      handleTakeOver(
                        currentConversation.conversation_id,
                        currentConversation.user_id
                      )
                    }
                    className="w-full whatsapp-pill"
                  >
                    Take Over
                  </button>
                )}
              </div>
            </div>
          )}

          {mobileDetailsOpen && (
            <div
              className="fixed inset-0 z-40 bg-black/40"
              onClick={() => setMobileDetailsOpen(false)}
            >
              <div
                className="absolute inset-x-0 bottom-0 rounded-t-3xl bg-white p-4 text-slate-900 shadow-2xl max-h-[80vh] overflow-y-auto"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="w-12 h-1.5 rounded-full bg-slate-300 mx-auto mb-4" />
                <div className="space-y-4">
                  <div>
                    <h3 className="font-semibold text-base">{String(currentConversation.user_name || currentConversation.user_id)}</h3>
                    <p className="text-sm text-slate-500">
                      {formatPhoneForDisplay(
                        currentConversation.user_phone || currentConversation.phone_number || ""
                      )}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-2xl bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">Language</p>
                      <p className="font-medium">
                        {String(currentConversation.language || "ar").toUpperCase()}
                      </p>
                    </div>
                    <div className="rounded-2xl bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">Gender</p>
                      <p className="font-medium capitalize">
                        {String(currentConversation.gender || "Unknown")}
                      </p>
                    </div>
                    <div className="rounded-2xl bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">Messages</p>
                      <p className="font-medium">
                        {currentConversation.message_count || currentHistory.length}
                      </p>
                    </div>
                    <div className="rounded-2xl bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">Status</p>
                      <div className="mt-1">
                        <StatusBadge status={String(currentConversation.status || "bot")} />
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl bg-slate-50 p-3 flex items-center justify-between">
                    <div>
                      <p className="text-xs text-slate-500">Sentiment</p>
                      <p className="font-medium capitalize">
                        {String(currentConversation.sentiment || "neutral")}
                      </p>
                    </div>
                    <SentimentIndicator sentiment={String(currentConversation.sentiment || "neutral")} />
                  </div>

                  <div className="space-y-2">
                    {currentConversation.status !== "human" ? (
                      <button
                        onClick={() =>
                          handleTakeOver(
                            currentConversation.conversation_id,
                            currentConversation.user_id
                          )
                        }
                        className="w-full btn-primary"
                      >
                        Take Over Conversation
                      </button>
                    ) : (
                      <button
                        onClick={() =>
                          handleReleaseToBot(
                            currentConversation.conversation_id,
                            currentConversation.user_id
                          )
                        }
                        className="w-full btn-secondary"
                      >
                        Release to Bot
                      </button>
                    )}
                    <button
                      onClick={() =>
                        handleEndConversation(
                          currentConversation.conversation_id,
                          currentConversation.user_id
                        )
                      }
                      className="w-full rounded-2xl px-4 py-3 bg-red-50 text-red-600 font-medium border border-red-200"
                    >
                      End Conversation
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default MobileLiveChatView;
