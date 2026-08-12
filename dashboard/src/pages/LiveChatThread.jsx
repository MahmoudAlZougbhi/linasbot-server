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
import { LiveChatBotOverlay } from "./LiveChatBotOverlay";
import { LiveChatThreadHeader } from "./LiveChatThreadHeader";
import { LiveChatThreadMessages } from "./LiveChatThreadMessages";

export function LiveChatThread(s) {
  const { selectedConversation, sidebarCollapsed, setBotPanelOpen, filteredBotConversations } = s;
  return (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className={`relative ${sidebarCollapsed ? "col-span-9" : "col-span-6"} whatsapp-chat-panel`}
        >
          <LiveChatBotOverlay {...s} />
          {selectedConversation ? (
            <>
              <LiveChatThreadHeader {...s} />
              <LiveChatThreadMessages {...s} />
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-400">
              <div className="text-center">
                <ChatBubbleLeftRightIcon className="w-16 h-16 mx-auto mb-4 text-slate-300" />
                <p className="text-lg font-medium mb-4">
                  Select a conversation to view
                </p>
                {sidebarCollapsed && (
                  <button
                    onClick={() => setBotPanelOpen(true)}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-50 hover:bg-primary-100 text-primary-700 font-medium"
                  >
                    <ChatBubbleLeftRightIcon className="w-5 h-5" />
                    With bot ({filteredBotConversations.length}) – Open list
                  </button>
                )}
              </div>
            </div>
          )}
        </motion.div>
  );
}
