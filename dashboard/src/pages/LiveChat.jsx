import { motion } from "framer-motion";
import MobileLiveChatView from "../components/LiveChat/MobileLiveChatView";
import { LiveChatDetails } from "./LiveChatDetails";
import { isSocialChannelUser } from "./LiveChat.helpers";
import { LiveChatModals } from "./LiveChatModals";
import { LiveChatSidebar } from "./LiveChatSidebar";
import { LiveChatThread } from "./LiveChatThread";
import { useLiveChatController } from "./useLiveChatController";

export { isSocialChannelUser };

/**
 * @param {{ mobile?: boolean }} props
 */
const LiveChat = ({ mobile = false }) => {
  const s = useLiveChatController({ mobile });
  const {
    isMobileView, formatLastRefreshTime, handleManualRefresh, isRefreshing,
    setMobileFilterSheetOpen, liveSearchQuery, setLiveSearchQuery, mobileListSection, setMobileListSection,
    filteredWaitingQueue, filteredWithOperator, filteredBotConversations, mobileVisibleConversations,
    isLoading, buildConversationFromQueueItem, getConversationUnreadCount, formatPhoneForDisplay,
    formatConversationListDate, openWaitingConversation, openConversation, mobileFilterSheetOpen,
    botDateFrom, setBotDateFrom, botDateTo, setBotDateTo, hasMoreChats, loadingMoreChats, loadMoreChats,
    selectedConversation, setSelectedConversation, reloadSelectedConversationMessages, messagesContainerRef,
    messagesLoading, messagesEndRef, handleFeedback, mobileDetailsOpen, setMobileDetailsOpen,
    handleTakeOver, handleReleaseToBot, handleEndConversation, selectedImage, discardImage, sendImageMessage,
    recordedAudio, discardRecording, sendVoiceMessage, isSendingVoice, imageInputRef, handleImageSelect,
    isRecording, recordingTime, stopRecording, startRecording, formatRecordingTime, messageInput,
    setMessageInput, handleSendMessage, isSending,
  } = s;

  if (isMobileView) {
    return (
      <>
        <MobileLiveChatView
          formatLastRefreshTime={formatLastRefreshTime}
          handleManualRefresh={handleManualRefresh}
          isRefreshing={isRefreshing}
          setMobileFilterSheetOpen={setMobileFilterSheetOpen}
          liveSearchQuery={liveSearchQuery}
          setLiveSearchQuery={setLiveSearchQuery}
          mobileListSection={mobileListSection}
          setMobileListSection={setMobileListSection}
          filteredWaitingQueue={filteredWaitingQueue}
          filteredWithOperator={filteredWithOperator}
          filteredBotConversations={filteredBotConversations}
          mobileVisibleConversations={mobileVisibleConversations}
          isLoading={isLoading}
          buildConversationFromQueueItem={buildConversationFromQueueItem}
          getConversationUnreadCount={getConversationUnreadCount}
          formatPhoneForDisplay={formatPhoneForDisplay}
          formatConversationListDate={formatConversationListDate}
          openWaitingConversation={openWaitingConversation}
          openConversation={openConversation}
          mobileFilterSheetOpen={mobileFilterSheetOpen}
          botDateFrom={botDateFrom}
          setBotDateFrom={setBotDateFrom}
          botDateTo={botDateTo}
          setBotDateTo={setBotDateTo}
          hasMoreChats={hasMoreChats}
          loadingMoreChats={loadingMoreChats}
          loadMoreChats={loadMoreChats}
          selectedConversation={selectedConversation}
          setSelectedConversation={setSelectedConversation}
          reloadSelectedConversationMessages={reloadSelectedConversationMessages}
          messagesContainerRef={messagesContainerRef}
          messagesLoading={messagesLoading}
          messagesEndRef={messagesEndRef}
          handleFeedback={handleFeedback}
          mobileDetailsOpen={mobileDetailsOpen}
          setMobileDetailsOpen={setMobileDetailsOpen}
          handleTakeOver={handleTakeOver}
          handleReleaseToBot={handleReleaseToBot}
          handleEndConversation={handleEndConversation}
          selectedImage={selectedImage}
          discardImage={discardImage}
          sendImageMessage={sendImageMessage}
          recordedAudio={recordedAudio}
          discardRecording={discardRecording}
          sendVoiceMessage={sendVoiceMessage}
          isSendingVoice={isSendingVoice}
          imageInputRef={imageInputRef}
          handleImageSelect={handleImageSelect}
          isRecording={isRecording}
          recordingTime={recordingTime}
          stopRecording={stopRecording}
          startRecording={startRecording}
          formatRecordingTime={formatRecordingTime}
          messageInput={messageInput}
          setMessageInput={setMessageInput}
          handleSendMessage={handleSendMessage}
          isSending={isSending}
        />
        <LiveChatModals {...s} />
      </>
    );
  }

  return (
    <>
    <div className="h-[calc(100vh-5rem)] -m-6 p-4 flex flex-col min-h-0">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-2 flex items-center justify-end flex-shrink-0"
      >
          <div className="flex items-center space-x-4">
            <button
              onClick={handleManualRefresh}
              disabled={isRefreshing}
              className={`flex items-center space-x-2 px-3 py-2 rounded-lg transition-all ${
                isRefreshing
                  ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                  : "bg-blue-50 text-blue-600 hover:bg-blue-100 active:scale-95"
              }`}
              title="Manually refresh conversations list"
            >
              <svg
                className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`}
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
              <span className="text-xs font-medium">
                {formatLastRefreshTime()}
              </span>
            </button>
          </div>
      </motion.div>

      <div className="grid grid-cols-12 gap-0 flex-1 min-h-0 whatsapp-shell overflow-hidden">
        <LiveChatSidebar {...s} />
        <LiveChatThread {...s} />
        <LiveChatDetails {...s} />
      </div>

      <LiveChatModals {...s} />
    </div>
    </>
  );
};

export default LiveChat;
