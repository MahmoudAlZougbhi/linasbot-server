import { MobileLiveChatListPane } from "./MobileLiveChatListPane";
import { MobileLiveChatThreadPane } from "./MobileLiveChatThreadPane";

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

  return (
    <div className="h-[100dvh] bg-slate-950 text-slate-100 flex flex-col overflow-hidden">
      {!currentConversation ? (
        <MobileLiveChatListPane
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
        />
      ) : (
        <MobileLiveChatThreadPane
          formatPhoneForDisplay={formatPhoneForDisplay}
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
      )}
    </div>
  );
};

export default MobileLiveChatView;
