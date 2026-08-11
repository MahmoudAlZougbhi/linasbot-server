import {
  ArrowRightIcon,
  ChevronLeftIcon,
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

/**
 * @param {{
 *   formatPhoneForDisplay: (phone: string | undefined) => string;
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
export const MobileLiveChatThreadPane = ({
  formatPhoneForDisplay,
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

  if (!currentConversation) return null;

  return (
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
  );
};
