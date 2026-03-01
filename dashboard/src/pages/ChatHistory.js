import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChatBubbleLeftRightIcon,
  UserIcon,
  ClockIcon,
  MagnifyingGlassIcon,
  FunnelIcon,
  ArrowPathIcon,
  PhoneIcon,
  CalendarDaysIcon,
  ChatBubbleLeftIcon,
  ChatBubbleOvalLeftEllipsisIcon,
} from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import toast from "react-hot-toast";
import {
  formatMessageTime,
  getTimezoneName,
} from "../utils/dateUtils";
import FeedbackModal from "../components/FeedbackModal";

// ✅ Helper function to get proxied audio URL for external sources
const getProxiedAudioUrl = (url) => {
  if (!url) return url;

  // Check if the URL is external (needs proxy)
  const isExternal = url.includes('whatsapp') ||
                     url.includes('mmc.api.montymobile.com') ||
                     url.includes('firebasestorage.googleapis.com') ||
                     url.includes('mmg.whatsapp.net') ||
                     (url.startsWith('http') && !url.includes(window.location.hostname));

  if (isExternal) {
    const baseURL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
      ? 'http://localhost:8003'
      : window.location.origin;
    return `${baseURL}/api/media/audio?url=${encodeURIComponent(url)}`;
  }

  return url;
};

// ✅ Modern WhatsApp-style audio player component
const ModernAudioPlayer = ({ audioUrl, isUserMessage = false }) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [error, setError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const audioRef = useRef(null);

  // Get the proxied URL for external audio sources
  const proxiedAudioUrl = getProxiedAudioUrl(audioUrl);

  const handlePlayPause = () => {
    if (audioRef.current && !error) {
      if (isPlaying) {
        audioRef.current.pause();
      } else {
        audioRef.current.play().catch((e) => {
          console.error("Audio play error:", e);
          setError(true);
        });
      }
      setIsPlaying(!isPlaying);
    }
  };

  const handleError = (e) => {
    console.error("Audio load error:", e, "URL:", audioUrl);
    setError(true);
    setIsLoading(false);
  };

  const handleCanPlay = () => {
    setIsLoading(false);
    setError(false);
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration);
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  const handleEnded = () => {
    setIsPlaying(false);
    if (audioRef.current) {
      audioRef.current.currentTime = 0;
      setCurrentTime(0);
    }
  };

  const handleProgressChange = (e) => {
    const newTime = parseFloat(e.target.value);
    if (audioRef.current) {
      audioRef.current.currentTime = newTime;
      setCurrentTime(newTime);
    }
  };

  const formatTime = (time) => {
    if (isNaN(time)) return "0:00";
    const minutes = Math.floor(time / 60);
    const seconds = Math.floor(time % 60);
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  };

  return (
    <div
      className={`flex items-center space-x-2 py-1 px-2 rounded-full ${
        isUserMessage ? "bg-white bg-opacity-20" : "bg-black bg-opacity-10"
      }`}
    >
      {/* Play/Pause Button */}
      <button
        onClick={handlePlayPause}
        className={`flex-shrink-0 p-2 rounded-full transition-all hover:scale-110 ${
          isUserMessage
            ? "bg-white bg-opacity-30 hover:bg-opacity-50 text-white"
            : "bg-white bg-opacity-20 hover:bg-opacity-40 text-slate-700"
        }`}
      >
        {isPlaying ? (
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M5 4a1 1 0 00-1 1v10a1 1 0 001 1h2a1 1 0 001-1V5a1 1 0 00-1-1H5zm8 0a1 1 0 00-1 1v10a1 1 0 001 1h2a1 1 0 001-1V5a1 1 0 00-1-1h-2z" clipRule="evenodd" />
          </svg>
        ) : (
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path d="M5.75 1.172A.5.5 0 005 1.65v16.7a.5.5 0 00.75.478l10.67-8.35a.5.5 0 000-.796L5.75 1.172z" />
          </svg>
        )}
      </button>

      {/* Progress Bar */}
      <div className="flex-1 flex flex-col space-y-1 min-w-[120px]">
        <input
          type="range"
          min="0"
          max={duration || 0}
          value={currentTime}
          onChange={handleProgressChange}
          className="w-full h-1 bg-white bg-opacity-30 rounded-full appearance-none cursor-pointer"
          style={{
            background: `linear-gradient(to right, ${
              isUserMessage ? "rgb(59, 130, 246)" : "rgb(71, 85, 105)"
            } ${(currentTime / duration) * 100}%, rgba(255,255,255,0.3) ${
              (currentTime / duration) * 100
            }%)`,
          }}
        />
        <div
          className={`text-xs font-medium ${
            isUserMessage ? "text-white" : "text-slate-600"
          }`}
        >
          {formatTime(currentTime)} / {formatTime(duration)}
        </div>
      </div>

      {/* Error message */}
      {error && (
        <span className="text-xs text-red-400 ml-2">Audio unavailable</span>
      )}

      {/* Loading indicator */}
      {isLoading && !error && (
        <span className="text-xs opacity-50 ml-2">Loading...</span>
      )}

      {/* Hidden audio element - uses proxied URL for external sources */}
      <audio
        ref={audioRef}
        src={proxiedAudioUrl}
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={handleTimeUpdate}
        onEnded={handleEnded}
        onError={handleError}
        onCanPlay={handleCanPlay}
      />
    </div>
  );
};

const ChatHistory = () => {
  const { loading, submitFeedback } = useApi();
  const appTimezone = getTimezoneName();
  const [customers, setCustomers] = useState([]);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [conversations, setConversations] = useState([]); // Conversation metadata only
  const [selectedConversationId, setSelectedConversationId] = useState(null);
  const [conversationMessages, setConversationMessages] = useState([]); // Messages for selected conversation
  const [messageCache, setMessageCache] = useState({}); // Cache messages by conversation ID
  const [searchTerm, setSearchTerm] = useState("");
  const [filterBy, setFilterBy] = useState("all"); // all, today, week, month
  const [isLoadingCustomers, setIsLoadingCustomers] = useState(false);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [feedbackModal, setFeedbackModal] = useState(null);
  const messagesEndRef = useRef(null);

  // Load customers on component mount
  useEffect(() => {
    loadCustomers();
  }, []);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [conversationMessages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const loadCustomers = async () => {
    setIsLoadingCustomers(true);
    try {
      const response = await fetch("/api/chat-history/customers");
      const data = await response.json();

      if (data.success) {
        setCustomers(data.customers || []);
      } else {
        toast.error("Failed to load customers");
      }
    } catch (error) {
      console.error("Error loading customers:", error);
      toast.error("Error loading customers");
    } finally {
      setIsLoadingCustomers(false);
    }
  };

  const loadConversations = async (customerId) => {
    setIsLoadingConversations(true);
    try {
      const response = await fetch(
        `/api/chat-history/conversations/${customerId}`
      );
      const data = await response.json();

      if (data.success) {
        const convList = data.conversations || [];
        // ✅ PRIORITY: Display conversations immediately
        setConversations(convList);
        setIsLoadingConversations(false);

        // Auto-select and lazy load first conversation if available
        if (convList.length > 0) {
          const firstConvId = convList[0].id;
          setSelectedConversationId(firstConvId);
          // ✅ Lazy load messages asynchronously - don't block UI
          loadConversationMessages(customerId, firstConvId);
        }
      } else {
        toast.error("Failed to load conversations");
        setIsLoadingConversations(false);
      }
    } catch (error) {
      console.error("Error loading conversations:", error);
      toast.error("Error loading conversations");
      setIsLoadingConversations(false);
    }
  };

  const loadConversationMessages = async (userId, conversationId) => {
    // Check cache first for instant loading
    if (messageCache[conversationId]) {
      setConversationMessages(messageCache[conversationId]);
      return;
    }

    // Create AbortController for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout

    setIsLoadingMessages(true);
    try {
      const response = await fetch(
        `/api/chat-history/messages/${userId}/${conversationId}`,
        { signal: controller.signal }
      );
      clearTimeout(timeoutId);

      const data = await response.json();

      if (data.success) {
        const messages = data.messages || [];
        // Cache the messages
        setMessageCache((prev) => ({
          ...prev,
          [conversationId]: messages,
        }));
        setConversationMessages(messages);
      } else {
        toast.error("Failed to load messages");
        setConversationMessages([]);
      }
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        console.error("Message fetch timed out after 60 seconds");
        toast.error("Loading messages timed out - conversation may have too many messages");
      } else {
        console.error("Error loading messages:", error);
        toast.error("Error loading messages");
      }
      setConversationMessages([]);
    } finally {
      setIsLoadingMessages(false);
    }
  };

  const handleCustomerSelect = (customer) => {
    setSelectedCustomer(customer);
    setSelectedConversationId(null);
    setConversationMessages([]);
    loadConversations(customer.user_id);
  };

  const handleConversationSelect = (conversationId) => {
    if (conversationId === selectedConversationId) return;
    setSelectedConversationId(conversationId);
    loadConversationMessages(selectedCustomer.user_id, conversationId);
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) return "";
    const now = new Date();
    const diffInHours = (now - date) / (1000 * 60 * 60);

    if (diffInHours < 24) {
      return new Intl.DateTimeFormat("en-US", {
        timeZone: appTimezone,
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      }).format(date);
    } else if (diffInHours < 168) {
      // 7 days
      return new Intl.DateTimeFormat("en-US", {
        timeZone: appTimezone,
        weekday: "short",
      }).format(date);
    } else {
      return new Intl.DateTimeFormat("en-US", {
        timeZone: appTimezone,
        month: "short",
        day: "numeric",
      }).format(date);
    }
  };

  const formatMessagePreview = (message) => {
    if (!message) return "No messages";
    if (message.length > 50) {
      return message.substring(0, 50) + "...";
    }
    return message;
  };

  // Feedback handlers
  const handleFeedback = (message, conversationId, feedbackType) => {
    if (feedbackType === "good") {
      // Submit positive feedback immediately
      submitFeedback({
        conversation_id: conversationId || `conv_${Date.now()}`,
        message_id: message.id || `msg_${Date.now()}`,
        user_question: getPreviousUserMessage(conversationId, message),
        bot_response: message.text,
        feedback_type: "good",
        language: "ar", // Default, could be detected from message
      });
      toast.success("👍 Thanks for your feedback!");
    } else if (feedbackType === "wrong") {
      // Show modal to get correct answer
      setFeedbackModal({
        message,
        conversationId,
        feedbackType,
      });
    }
  };

  const getPreviousUserMessage = (conversationId, botMessage) => {
    // Use the currently loaded messages (from conversationMessages)
    if (!conversationMessages || conversationMessages.length === 0) return "Unknown question";

    const botIndex = conversationMessages.findIndex((m) => m === botMessage);

    // Find the previous user message
    for (let i = botIndex - 1; i >= 0; i--) {
      if (conversationMessages[i].role === "user") {
        return conversationMessages[i].text;
      }
    }

    return "Unknown question";
  };

  const submitCorrection = async (correctAnswer, feedbackReason) => {
    const result = await submitFeedback({
      conversation_id: feedbackModal.conversationId || `conv_${Date.now()}`,
      message_id: feedbackModal.message.id || `msg_${Date.now()}`,
      user_question: getPreviousUserMessage(
        feedbackModal.conversationId,
        feedbackModal.message
      ),
      bot_response: feedbackModal.message.text,
      feedback_type: "wrong",
      correct_answer: correctAnswer,
      feedback_reason: feedbackReason,
      language: "ar", // Default, could be detected from message
    });

    if (result.success) {
      setFeedbackModal(null);
    }
  };

  const filteredCustomers = customers.filter((customer) => {
    const matchesSearch =
      customer.user_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      customer.user_id?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      customer.phone_full?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      customer.phone_clean?.toLowerCase().includes(searchTerm.toLowerCase());

    if (!matchesSearch) return false;

    if (filterBy === "all") return true;

    const lastMessageTime = new Date(customer.last_message_time);
    const now = new Date();
    const diffInHours = (now - lastMessageTime) / (1000 * 60 * 60);

    switch (filterBy) {
      case "today":
        return diffInHours < 24;
      case "week":
        return diffInHours < 168; // 7 days
      case "month":
        return diffInHours < 720; // 30 days
      default:
        return true;
    }
  });

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="bg-white border-b border-slate-200 px-6 py-4"
      >
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold gradient-text font-display">
              💬 Chat History
            </h1>
            <p className="text-slate-600 mt-1">
              Review all customer conversations and chat history
            </p>
          </div>
          <button
            onClick={loadCustomers}
            disabled={isLoadingCustomers}
            className="btn-secondary flex items-center space-x-2"
          >
            <ArrowPathIcon
              className={`w-4 h-4 ${isLoadingCustomers ? "animate-spin" : ""}`}
            />
            <span>Refresh</span>
          </button>
        </div>
      </motion.div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel - Customer List */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="w-1/3 bg-white border-r border-slate-200 flex flex-col"
        >
          {/* Search and Filter */}
          <div className="p-4 border-b border-slate-200">
            <div className="relative mb-3">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search customers..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="input-field pl-10 w-full"
              />
            </div>
            <div className="flex space-x-2">
              {[
                { key: "all", label: "All", icon: ChatBubbleLeftRightIcon },
                { key: "today", label: "Today", icon: ClockIcon },
                { key: "week", label: "Week", icon: CalendarDaysIcon },
                { key: "month", label: "Month", icon: FunnelIcon },
              ].map((filter) => (
                <button
                  key={filter.key}
                  onClick={() => setFilterBy(filter.key)}
                  className={`flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    filterBy === filter.key
                      ? "bg-primary-100 text-primary-700"
                      : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  <filter.icon className="w-3 h-3" />
                  <span>{filter.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Customer List */}
          <div className="flex-1 overflow-y-auto">
            {isLoadingCustomers ? (
              <div className="flex items-center justify-center h-32">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
              </div>
            ) : filteredCustomers.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 text-slate-500">
                <ChatBubbleLeftIcon className="w-8 h-8 mb-2" />
                <p className="text-sm">No conversations found</p>
              </div>
            ) : (
              <div className="space-y-1 p-2">
                {filteredCustomers.map((customer) => (
                  <motion.div
                    key={customer.user_id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    whileHover={{ scale: 1.02 }}
                    onClick={() => handleCustomerSelect(customer)}
                    className={`p-3 rounded-lg cursor-pointer transition-all duration-200 ${
                      selectedCustomer?.user_id === customer.user_id
                        ? "bg-primary-50 border border-primary-200"
                        : "hover:bg-slate-50 border border-transparent"
                    }`}
                  >
                    <div className="flex items-start space-x-3">
                      <div className="flex-shrink-0">
                        <div className="w-10 h-10 bg-gradient-to-br from-primary-400 to-secondary-400 rounded-full flex items-center justify-center">
                          <UserIcon className="w-5 h-5 text-white" />
                        </div>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-slate-900 truncate">
                            {customer.user_name || "Unknown User"}
                          </p>
                          <span className="text-xs text-slate-500">
                            {formatTime(customer.last_message_time)}
                          </span>
                        </div>
                        <div className="flex items-center space-x-1 mt-1">
                          <PhoneIcon className="w-3 h-3 text-slate-400" />
                          <p className="text-xs text-slate-500 truncate">
                            {customer.phone_full || customer.user_id}
                          </p>
                        </div>
                        <p className="text-xs text-slate-600 mt-1 truncate">
                          {formatMessagePreview(customer.last_message)}
                        </p>
                        <div className="flex items-center justify-between mt-2">
                          <span className="text-xs text-slate-500">
                            {customer.message_count} messages
                          </span>
                          {customer.unread_count > 0 && (
                            <span className="bg-primary-500 text-white text-xs px-2 py-0.5 rounded-full">
                              {customer.unread_count}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </motion.div>

        {/* Right Panel - Chat View */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="flex-1 flex flex-col bg-slate-50"
        >
          {selectedCustomer ? (
            <>
              {/* Chat Header */}
              <div className="bg-white border-b border-slate-200 px-6 py-4">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 bg-gradient-to-br from-primary-400 to-secondary-400 rounded-full flex items-center justify-center">
                    <UserIcon className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900">
                      {selectedCustomer.user_name || "Unknown User"}
                    </h3>
                    <div className="flex items-center space-x-2 text-sm text-slate-500">
                      <PhoneIcon className="w-3 h-3" />
                      <span>
                        {selectedCustomer.phone_full ||
                          selectedCustomer.user_id}
                      </span>
                      <span>•</span>
                      <span>{selectedCustomer.message_count} messages</span>
                      {selectedCustomer.gender && selectedCustomer.gender !== "unknown" && (
                        <>
                          <span>•</span>
                          <span className="capitalize">{selectedCustomer.gender}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Conversation Selector - only show if multiple conversations */}
              {conversations.length > 1 && (
                <div className="bg-white border-b border-slate-200 px-4 py-2">
                  <div className="flex space-x-2 overflow-x-auto">
                    {conversations.map((conv, idx) => (
                      <button
                        key={conv.id}
                        onClick={() => handleConversationSelect(conv.id)}
                        className={`flex-shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                          selectedConversationId === conv.id
                            ? "bg-primary-100 text-primary-700"
                            : "text-slate-600 hover:bg-slate-100"
                        }`}
                      >
                        Conv {idx + 1} ({conv.message_count} msgs)
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {isLoadingConversations || isLoadingMessages ? (
                  <div className="flex items-center justify-center h-32">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
                  </div>
                ) : conversationMessages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-32 text-slate-500">
                    <ChatBubbleOvalLeftEllipsisIcon className="w-8 h-8 mb-2" />
                    <p className="text-sm">No messages found</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {conversationMessages.map((message, index) => {
                      // Check if this is a voice message
                      const isVoiceMessage =
                        message.type === "voice" ||
                        message.content === "[رسالة صوتية]" ||
                        message.content === "رسالة صوتية" ||
                        message.audio_url;

                      // Check if this is an image message
                      const isImageMessage =
                        message.type === "image" ||
                        message.content === "[صورة]" ||
                        message.image_url;

                      return (
                        <motion.div
                          key={index}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: Math.min(index * 0.05, 0.5) }}
                          className={`flex ${
                            message.role === "user"
                              ? "justify-end"
                              : "justify-start"
                          }`}
                        >
                          <div
                            className={`max-w-xs lg:max-w-md ${
                              message.role === "user" ? "" : "flex flex-col"
                            }`}
                          >
                            <div
                              className={`px-4 py-2 rounded-2xl ${
                                message.role === "user"
                                  ? "bg-primary-500 text-white"
                                  : "bg-white text-slate-900 border border-slate-200"
                              }`}
                            >
                              {/* Image Message Display */}
                              {isImageMessage ? (
                                <div className="flex flex-col space-y-2">
                                  {message.image_url ? (
                                    <div className="max-w-xs">
                                      <img
                                        src={message.image_url}
                                        alt="User image"
                                        className="rounded-lg max-w-full h-auto object-cover"
                                        onError={(e) => {
                                          e.target.src =
                                            "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect fill='%23e5e7eb' width='100' height='100'/%3E%3Ctext x='50' y='50' text-anchor='middle' dy='.3em' fill='%23999' font-size='12'%3EImage unavailable%3C/text%3E%3C/svg%3E";
                                        }}
                                      />
                                    </div>
                                  ) : (
                                    <div className="flex items-center space-x-2">
                                      <span className="text-sm">صورة</span>
                                      <span className="text-xs opacity-75">
                                        (رابط غير متاح)
                                      </span>
                                    </div>
                                  )}
                                </div>
                              ) : isVoiceMessage ? (
                                /* Voice Message Display */
                                <div className="flex items-start space-x-3">
                                  <div className="flex-shrink-0">
                                    <svg
                                      className="w-8 h-8"
                                      fill={
                                        message.role === "user"
                                          ? "currentColor"
                                          : "currentColor"
                                      }
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
                                    {message.audio_url ? (
                                      <div>
                                        {/* Modern WhatsApp-style audio player */}
                                        <ModernAudioPlayer
                                          audioUrl={message.audio_url}
                                          isUserMessage={
                                            message.role === "user"
                                          }
                                        />
                                        {/* Show transcribed text below audio player */}
                                        {message.text &&
                                          message.text !== "[رسالة صوتية]" &&
                                          message.text !== "رسالة صوتية" && (
                                            <p className="text-xs mt-2 opacity-90">
                                              {message.text}
                                            </p>
                                          )}
                                      </div>
                                    ) : (
                                      <div className="flex items-center space-x-2">
                                        <span className="text-sm">
                                          رسالة صوتية
                                        </span>
                                        <span className="text-xs opacity-75">
                                          (URL not available)
                                        </span>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ) : (
                                /* Text Message Display */
                                <p className="text-sm whitespace-pre-wrap">
                                  {message.text}
                                </p>
                              )}

                              {/* Timestamp and Feedback */}
                              <div
                                className={`flex items-center space-x-2 mt-1 ${
                                  message.role === "user"
                                    ? "text-primary-100"
                                    : "text-slate-500"
                                }`}
                              >
                                <span className="text-xs">
                                  {formatMessageTime(message.timestamp)}
                                </span>
                                {message.role !== "user" && (
                                  <>
                                    <span className="text-xs">• 🤖 Bot</span>
                                    <div className="flex items-center space-x-1 ml-2">
                                      <button
                                        onClick={() =>
                                          handleFeedback(
                                            message,
                                            selectedConversationId,
                                            "good"
                                          )
                                        }
                                        className="text-xs hover:scale-125 transition-transform"
                                        title="Good response"
                                      >
                                        👍
                                      </button>
                                      <button
                                        onClick={() =>
                                          handleFeedback(
                                            message,
                                            selectedConversationId,
                                            "wrong"
                                          )
                                        }
                                        className="text-xs hover:scale-125 transition-transform"
                                        title="Wrong answer - train bot"
                                      >
                                        👎
                                      </button>
                                    </div>
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <ChatBubbleLeftRightIcon className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-900 mb-2">
                  Select a Customer
                </h3>
                <p className="text-slate-500">
                  Choose a customer from the left panel to view their chat
                  history
                </p>
              </div>
            </div>
          )}
        </motion.div>
      </div>

      {/* Feedback Modal */}
      {feedbackModal && (
        <FeedbackModal
          message={{ content: feedbackModal.message.text }}
          conversation={{ conversation_id: feedbackModal.conversationId }}
          onClose={() => setFeedbackModal(null)}
          onSubmit={submitCorrection}
        />
      )}
    </div>
  );
};

export default ChatHistory;
