import React, { useState, useEffect, useRef } from "react";
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
  SignalIcon,
  XMarkIcon,
  ChartBarIcon,
  MicrophoneIcon,
  PhotoIcon,
  MagnifyingGlassIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { useApi } from "../hooks/useApi";
import { formatMessageTime } from "../utils/dateUtils";
import FeedbackModal from "../components/FeedbackModal";
import LikeFeedbackModal from "../components/LikeFeedbackModal";
import ModernAudioPlayer from "../components/LiveChat/ModernAudioPlayer";
import {
  SentimentIndicator,
  StatusBadge,
} from "../components/LiveChat/ConversationIndicators";
import { useLiveChatSSE } from "../hooks/useLiveChatSSE";
import { useLiveChatMediaComposer } from "../hooks/useLiveChatMediaComposer";
import {
  endLiveChatConversation,
  fetchLiveChatConversationMessages,
} from "../utils/liveChatApi";

const LiveChat = () => {
  const [activeConversations, setActiveConversations] = useState([]);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [waitingQueue, setWaitingQueue] = useState([]);
  const [messageInput, setMessageInput] = useState("");
  const [operatorStatus, setOperatorStatus] = useState("available");
  const [isLoading, setIsLoading] = useState(true);
  const [useMockData, setUseMockData] = useState(false);
  const [feedbackModal, setFeedbackModal] = useState(null);

  // ✅ Auto-refresh state (Solution 1 + 4: Smart refresh with badges)
  const [lastRefreshTime, setLastRefreshTime] = useState(new Date());
  const [newConversationIds, setNewConversationIds] = useState(new Set()); // Track new conversations
  const [isRefreshing, setIsRefreshing] = useState(false);

  // ✅ Send button race condition state
  const [isSending, setIsSending] = useState(false);

  // ✅ Messages loading state for lazy loading
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [loadingMoreMessages, setLoadingMoreMessages] = useState(false);
  const [hasMoreMessages, setHasMoreMessages] = useState(true);

  // ✅ Search by name or phone (debounced for API calls)
  const [liveSearchQuery, setLiveSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  // ✅ WhatsApp-style: top 30, Load More
  const [chatPage, setChatPage] = useState(1);
  const [hasMoreChats, setHasMoreChats] = useState(false);
  const [loadingMoreChats, setLoadingMoreChats] = useState(false);

  const messagesContainerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const selectedConversationRef = useRef(null);
  const activeConversationsRef = useRef([]); // ✅ Ref to track current conversations (fixes stale closure)
  const useMockDataRef = useRef(false); // ✅ Ref to track mock data status (fixes stale closure)
  const debouncedSearchRef = useRef("");
  const isMountedRef = useRef(true); // ✅ Prevent setState after unmount (fixes slow-down on repeated opens)
  const previousConversationIdRef = useRef(null);
  const previousMessageCountRef = useRef(0);

  // Keep refs in sync with state
  useEffect(() => {
    selectedConversationRef.current = selectedConversation;
  }, [selectedConversation]);

  useEffect(() => {
    activeConversationsRef.current = activeConversations;
  }, [activeConversations]);

  useEffect(() => {
    useMockDataRef.current = useMockData;
  }, [useMockData]);

  // Track mount state to avoid setState after unmount (fixes slowdown on repeated open/close)
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Debounce search input (250ms) - WhatsApp-style snappy
  useEffect(() => {
    const timer = setTimeout(() => {
      const trimmed = liveSearchQuery.trim();
      setDebouncedSearch(trimmed);
      debouncedSearchRef.current = trimmed;
    }, 250);
    return () => clearTimeout(timer);
  }, [liveSearchQuery]);

  const {
    getUnifiedChats,
    getLiveConversations,
    getWaitingQueue,
    takeoverConversation,
    releaseConversation,
    sendOperatorMessage,
    updateOperatorStatus,
    submitFeedback,
  } = useApi();

  useEffect(() => {
    updateOperatorStatus("operator_001", operatorStatus).catch(() => {
      // Keep UI responsive even if status update endpoint is temporarily unavailable.
    });
  }, [operatorStatus, updateOperatorStatus]);

  // Fetch conversation messages - WhatsApp-style: last 50 initially, Load More with before
  const fetchConversationMessages = async (userId, conversationId, days = 0, before = null, limit = 50) => {
    try {
      const data = await fetchLiveChatConversationMessages({
        userId,
        conversationId,
        days,
        before,
        limit,
      });

      if (data.success && data.messages) {
        return { messages: data.messages, hasMore: data.has_more ?? false };
      }
      console.warn("No messages found or API error:", data);
      return { messages: [], hasMore: false };
    } catch (error) {
      if (error.name === 'AbortError') {
        console.error("Message fetch timed out");
        toast.error("Loading messages timed out - try again");
      } else {
        console.error("Error fetching conversation messages:", error);
      }
      return { messages: [], hasMore: false };
    }
  };

  const appendMessageToSelectedConversation = (newMessage) => {
    setSelectedConversation((previous) => {
      if (!previous) return previous;
      return {
        ...previous,
        history: [...(previous.history || []), newMessage],
      };
    });
  };

  const {
    isRecording,
    recordedAudio,
    recordingTime,
    isSendingVoice,
    selectedImage,
    imageInputRef,
    startRecording,
    stopRecording,
    discardRecording,
    sendVoiceMessage,
    formatRecordingTime,
    handleImageSelect,
    discardImage,
    sendImageMessage,
  } = useLiveChatMediaComposer({
    selectedConversation,
    sendOperatorMessage,
    onAppendMessage: appendMessageToSelectedConversation,
  });

  // Fetch real data from API
  useEffect(() => {
    const fetchLiveData = async () => {
      if (!isMountedRef.current) return;
      // Only show loading on initial load, not on refresh
      if (!activeConversations.length) {
        if (isMountedRef.current) setIsLoading(true);
      }

      try {
        let chatsResponse;
        try {
          chatsResponse = await getUnifiedChats(debouncedSearch, 1, 30);
          if (!isMountedRef.current) return;
        } catch (err) {
          if (err?.response?.status === 504 || err?.code === "ECONNABORTED") {
            try {
              const fallback = await getLiveConversations(debouncedSearch);
              chatsResponse = fallback.success && fallback.conversations
                ? { success: true, chats: fallback.conversations, has_more: false }
                : { success: false, chats: [] };
              if (chatsResponse.success) {
                toast("Showing live chats only (server busy)", { icon: "⚡" });
              } else {
                throw new Error("Fallback failed");
              }
            } catch (fallbackErr) {
              // 504 / timeout: do NOT switch to mock data - keep existing conversations
              toast.error("Server is busy. Data will refresh when available.");
              return; // Exit without changing conversations or loading mock
            }
          } else {
            throw err;
          }
        }
        if (chatsResponse?.success && isMountedRef.current) {
          const chats = chatsResponse.chats || chatsResponse.conversations || [];
          setActiveConversations(chats);
          setChatPage(1);
          setHasMoreChats(chatsResponse.has_more || false);
          setUseMockData(false);

          const currentSelection = selectedConversationRef.current;

          if (
            !currentSelection &&
            chats.length > 0 &&
            !activeConversations.length
          ) {
            const firstConv = chats[0];
            // ✅ Set conversation immediately with empty history (show loading state)
            setSelectedConversation({
              conversation: firstConv,
              history: [],
            });
            setMessagesLoading(true);
          } else if (currentSelection) {
            const updatedConv = chats.find(
              (c) =>
                c.conversation_id ===
                currentSelection.conversation.conversation_id
            );
            if (updatedConv && isMountedRef.current) {
              setSelectedConversation((prev) => ({
                ...prev,
                conversation: updatedConv,
              }));
            }
          }
        } else if (isMountedRef.current) {
          // Backend returned failure - use mock only for true offline (ERR_NETWORK)
          if (!activeConversations.length) {
            loadMockData();
          }
        }

        // Fetch waiting queue in background (do not block initial Live Chat render)
        getWaitingQueue()
          .then((queueResponse) => {
            if (!isMountedRef.current) return;
            if (queueResponse?.success && queueResponse.queue) {
              setWaitingQueue(queueResponse.queue);
            }
          })
          .catch(() => {
            // Silent fail - chats list already rendered
          });
      } catch (error) {
        if (!isMountedRef.current) return;
        console.error("Error fetching live chat data:", error);
        const is504OrTimeout = error?.response?.status === 504 || error?.code === "ECONNABORTED";
        if (is504OrTimeout) {
          toast.error("Server is busy. Will retry automatically.");
        } else if (!activeConversations.length) {
          loadMockData();
        }
      } finally {
        if (isMountedRef.current) setIsLoading(false);
      }
    };

    fetchLiveData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]); // Re-fetch when search changes

  useLiveChatSSE({
    enabled: !useMockData,
    isMountedRef,
    useMockDataRef,
    activeConversationsRef,
    selectedConversationRef,
    debouncedSearchRef,
    getUnifiedChats,
    fetchConversationMessages,
    setActiveConversations,
    setNewConversationIds,
    setLastRefreshTime,
    setIsRefreshing,
    setSelectedConversation,
  });

  const selectedConversationId = selectedConversation?.conversation?.conversation_id;
  const selectedConversationUserId = selectedConversation?.conversation?.user_id;

  // ✅ Fetch messages when selected conversation changes (not polling)
  useEffect(() => {
    if (!selectedConversationId || !selectedConversationUserId || useMockData) {
      setMessagesLoading(false);
      return;
    }

    let cancelled = false;
    const fetchMessages = async () => {
      setMessagesLoading(true);
      try {
        const { messages, hasMore } = await fetchConversationMessages(
          selectedConversationUserId,
          selectedConversationId,
          0,
          null,
          50
        );
        if (!isMountedRef.current || cancelled) return;

        setSelectedConversation((prev) => {
          if (!prev || prev.conversation?.conversation_id !== selectedConversationId) {
            return prev;
          }
          return { ...prev, history: messages || [] };
        });
        setHasMoreMessages(hasMore);
      } catch (error) {
        // Silent fail
      } finally {
        if (isMountedRef.current && !cancelled) {
          setMessagesLoading(false);
        }
      }
    };

    fetchMessages();

    return () => {
      cancelled = true;
    };
  }, [selectedConversationId, selectedConversationUserId, useMockData]);

  // Load mock data fallback
  const loadMockData = () => {
    setUseMockData(true);
    const mockConversations = [
      {
        conversation_id: "conv_001",
        user_id: "mock_user_001",
        user_name: "Sarah Ahmed",
        user_phone: "+961 70 123456",
        status: "bot",
        language: "ar",
        message_count: 12,
        last_activity: new Date().toISOString(),
        duration_seconds: 245,
        sentiment: "positive",
        last_message: {
          content: "متى يمكنني الحجز؟",
          is_user: true,
          timestamp: new Date().toISOString(),
        },
      },
      {
        conversation_id: "conv_002",
        user_id: "mock_user_002",
        user_name: "Marie Dubois",
        user_phone: "+961 71 234567",
        status: "human",
        language: "fr",
        message_count: 8,
        last_activity: new Date(Date.now() - 60000).toISOString(),
        duration_seconds: 180,
        operator_id: "op_001",
        sentiment: "neutral",
        last_message: {
          content: "Combien coûte le traitement?",
          is_user: true,
          timestamp: new Date(Date.now() - 60000).toISOString(),
        },
      },
      {
        conversation_id: "conv_003",
        user_id: "mock_user_003",
        user_name: "John Smith",
        user_phone: "+961 76 345678",
        status: "waiting_human",
        language: "en",
        message_count: 5,
        last_activity: new Date(Date.now() - 120000).toISOString(),
        duration_seconds: 120,
        sentiment: "negative",
        last_message: {
          content: "I need urgent help!",
          is_user: true,
          timestamp: new Date(Date.now() - 120000).toISOString(),
        },
      },
    ];

    const mockQueue = [
      {
        conversation_id: "conv_003",
        user_id: "mock_user_003",
        user_name: "John Smith",
        user_phone: "+961 76 345678",
        language: "en",
        reason: "urgent_detected",
        wait_time_seconds: 120,
        sentiment: "negative",
        message_count: 5,
      },
      {
        conversation_id: "conv_004",
        user_id: "mock_user_004",
        user_name: "Fatima Hassan",
        user_phone: "+961 03 456789",
        language: "ar",
        reason: "user_request",
        wait_time_seconds: 45,
        sentiment: "neutral",
        message_count: 3,
      },
    ];

    setActiveConversations(mockConversations);
    setWaitingQueue(mockQueue);

    // Simulate conversation history
    if (!selectedConversation) {
      const mockHistory = [
        {
          timestamp: new Date(Date.now() - 300000).toISOString(),
          is_user: true,
          content: "مرحبا، أريد معلومات عن إزالة الشعر بالليزر",
          type: "text",
        },
        {
          timestamp: new Date(Date.now() - 280000).toISOString(),
          is_user: false,
          content:
            "أهلاً وسهلاً! يسعدني مساع��تك. لدينا أحدث أجهزة الليزر لإزالة الشعر بفعالية وأمان.",
          type: "text",
          handled_by: "bot",
        },
        {
          timestamp: new Date(Date.now() - 250000).toISOString(),
          is_user: true,
          content: "كم عدد الجلسات المطلوبة؟",
          type: "text",
        },
        {
          timestamp: new Date(Date.now() - 240000).toISOString(),
          is_user: false,
          content:
            "عادة ما تحتاج إلى 6-8 جلسات للحصول على نتائج مثالية، مع فاصل 4-6 أسابيع بين كل جلسة.",
          type: "text",
          handled_by: "bot",
        },
        {
          timestamp: new Date(Date.now() - 200000).toISOString(),
          is_user: true,
          content: "والأسعار؟",
          type: "text",
        },
        {
          timestamp: new Date(Date.now() - 180000).toISOString(),
          is_user: false,
          content:
            "الأسعار تختلف حسب المنطقة المراد معالجتها. يمكنك زيارتنا للحصول على استشارة مجانية وعرض سعر مخصص.",
          type: "text",
          handled_by: "bot",
        },
      ];

      if (mockConversations[0]) {
        setSelectedConversation({
          conversation: mockConversations[0],
          history: mockHistory,
        });
      }
    }
  };

  // ✅ Load more chats (WhatsApp-style pagination)
  const loadMoreChats = async () => {
    if (loadingMoreChats || !hasMoreChats) return;
    setLoadingMoreChats(true);
    try {
      const nextPage = chatPage + 1;
      const chatsResponse = await getUnifiedChats(debouncedSearch, nextPage, 30);
      if (chatsResponse.success && chatsResponse.chats) {
        setActiveConversations((prev) => [...prev, ...chatsResponse.chats]);
        setChatPage(nextPage);
        setHasMoreChats(chatsResponse.has_more || false);
      }
    } catch (error) {
      console.error("Error loading more chats:", error);
    } finally {
      setLoadingMoreChats(false);
    }
  };

  // ✅ Manual refresh handler
  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    try {
      const chatsResponse = await getUnifiedChats(debouncedSearch, 1, 30);
      if (chatsResponse.success && chatsResponse.chats) {
        const chats = chatsResponse.chats;
        const previousIds = new Set(
          activeConversationsRef.current.map((c) => c.conversation_id)
        );
        const newIds = new Set(
          chats.filter((c) => !previousIds.has(c.conversation_id)).map((c) => c.conversation_id)
        );

        setActiveConversations(chats);
        setChatPage(1);
        setHasMoreChats(chatsResponse.has_more || false);
        setNewConversationIds(newIds);
        setLastRefreshTime(new Date());
        toast.success("Conversations refreshed");

        // Auto-clear "new" badge after 10 seconds
        if (newIds.size > 0) {
          setTimeout(() => {
            setNewConversationIds(new Set());
          }, 10000);
        }
      }
    } catch (error) {
      console.error("Error refreshing conversations:", error);
      if (error.code === "ECONNABORTED") {
        toast.error("Request timeout - server may be busy. Try again.");
      } else {
        toast.error("Failed to refresh conversations");
      }
    } finally {
      setIsRefreshing(false);
    }
  };

  // ✅ Format last refresh time as relative time (e.g., "2 seconds ago")
  const formatLastRefreshTime = () => {
    const now = new Date();
    const diff = Math.floor((now - lastRefreshTime) / 1000); // seconds

    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  };

  // ✅ Load more (older) messages - cursor-based: before=oldest loaded timestamp
  const loadMoreMessages = async () => {
    if (!selectedConversation || loadingMoreMessages || !hasMoreMessages) return;
    const history = selectedConversation.history || [];
    const sorted = [...history].sort(
      (a, b) => new Date(a?.timestamp || 0).getTime() - new Date(b?.timestamp || 0).getTime()
    );
    const beforeTs = sorted.length > 0 && sorted[0]?.timestamp
      ? sorted[0].timestamp
      : new Date().toISOString();
    setLoadingMoreMessages(true);
    try {
      const { messages: older, hasMore } = await fetchConversationMessages(
        selectedConversation.conversation.user_id,
        selectedConversation.conversation.conversation_id,
        0,
        beforeTs,
        50
      );
      if (older && older.length > 0) {
        // Prepend older messages; dedupe by message_id
        setSelectedConversation((prev) => {
          const prevHistory = prev?.history || [];
          const seen = new Set(prevHistory.map((m) => m.message_id).filter(Boolean));
          const newOlder = older.filter((m) => !m.message_id || !seen.has(m.message_id));
          const combined = [...newOlder, ...prevHistory];
          const deduped = combined
            .filter((m, i, arr) => {
              const id = m.message_id;
              if (!id) return true;
              return arr.findIndex((x) => x.message_id === id) === i;
            })
            .sort((a, b) => new Date(a?.timestamp || 0).getTime() - new Date(b?.timestamp || 0).getTime());
          return { ...prev, history: deduped };
        });
      }
      setHasMoreMessages(hasMore);
    } catch (e) {
      console.error("Load more messages error:", e);
    } finally {
      setLoadingMoreMessages(false);
    }
  };

  // ✅ Reload messages for currently selected conversation (WhatsApp-style: last 50)
  const reloadSelectedConversationMessages = async () => {
    if (!selectedConversation) return;

    try {
      const { messages, hasMore } = await fetchConversationMessages(
        selectedConversation.conversation.user_id,
        selectedConversation.conversation.conversation_id,
        0,
        null,
        50
      );
      setSelectedConversation((prev) => ({
        ...prev,
        history: messages || [],
      }));
      setHasMoreMessages(hasMore);
      toast.success(`Loaded ${(messages || []).length} messages`);
    } catch (error) {
      console.error("Error reloading conversation messages:", error);
      toast.error("Failed to reload messages");
    }
  };

  // Auto-scroll only on conversation switch or when user is near bottom.
  useEffect(() => {
    const conversationId = selectedConversation?.conversation?.conversation_id || null;
    const messageCount = selectedConversation?.history?.length || 0;
    const previousConversationId = previousConversationIdRef.current;
    const previousMessageCount = previousMessageCountRef.current;

    const hasConversationChanged =
      conversationId && conversationId !== previousConversationId;
    const hasNewMessages = messageCount > previousMessageCount;

    const container = messagesContainerRef.current;
    const nearBottom = container
      ? container.scrollHeight - container.scrollTop - container.clientHeight < 120
      : true;

    if (hasConversationChanged || (hasNewMessages && nearBottom)) {
      const behavior = hasConversationChanged ? "auto" : "smooth";
      messagesEndRef.current?.scrollIntoView({ behavior });
    }

    previousConversationIdRef.current = conversationId;
    previousMessageCountRef.current = messageCount;
  }, [selectedConversation?.conversation?.conversation_id, selectedConversation?.history?.length]);

  const handleTakeOver = async (conversationId, userId) => {
    console.log("🔄 handleTakeOver called with:", { conversationId, userId });

    if (!conversationId || !userId) {
      console.error("❌ Missing conversationId or userId:", { conversationId, userId });
      toast.error("Cannot take over: missing conversation or user ID");
      return;
    }

    try {
      const result = await takeoverConversation(
        conversationId,
        userId,
        "operator_001"
      );

      console.log("📋 Takeover result:", result);

      if (result.success) {
        toast.success("Conversation taken over successfully");
        // Update conversation status locally
        setActiveConversations((prev) =>
          prev.map((conv) =>
            conv.conversation_id === conversationId
              ? { ...conv, status: "human", operator_id: "operator_001" }
              : conv
          )
        );
        // Update selected conversation if it's the one we took over
        if (
          selectedConversation?.conversation?.conversation_id === conversationId
        ) {
          setSelectedConversation((prev) => ({
            ...prev,
            conversation: {
              ...prev.conversation,
              status: "human",
              operator_id: "operator_001",
            },
          }));
        }
        // Remove from queue
        setWaitingQueue((prev) =>
          prev.filter((item) => item.conversation_id !== conversationId)
        );
      } else {
        console.error("❌ Takeover failed:", result.error);
        toast.error(`Failed to take over: ${result.error || "Unknown error"}`);
      }
    } catch (error) {
      console.error("❌ Error taking over conversation:", error);
      toast.error(`Error: ${error.message || "Unknown error"}`);
    }
  };

  const handleReleaseToBot = async (conversationId, userId) => {
    try {
      const result = await releaseConversation(conversationId, userId);

      if (result.success) {
        toast.success("Conversation released to bot");
        // Update conversation status locally
        setActiveConversations((prev) =>
          prev.map((conv) =>
            conv.conversation_id === conversationId
              ? { ...conv, status: "bot", operator_id: null }
              : conv
          )
        );
        // Update selected conversation if it's the one we released
        if (
          selectedConversation?.conversation?.conversation_id === conversationId
        ) {
          setSelectedConversation((prev) => ({
            ...prev,
            conversation: {
              ...prev.conversation,
              status: "bot",
              operator_id: null,
            },
          }));
        }
      } else {
        toast.error("Failed to release conversation");
      }
    } catch (error) {
      console.error("Error releasing conversation:", error);
      toast.error("Error releasing conversation");
    }
  };

  const handleEndConversation = async (conversationId, userId) => {
    try {
      const result = await endLiveChatConversation({
        conversationId,
        userId,
        operatorId: "operator_001",
      });

      if (result.success) {
        toast.success("Conversation ended successfully");
        // Remove from active conversations
        setActiveConversations((prev) =>
          prev.filter((conv) => conv.conversation_id !== conversationId)
        );
        // Clear selection if it was the ended conversation
        if (
          selectedConversation?.conversation?.conversation_id === conversationId
        ) {
          setSelectedConversation(null);
        }
      } else {
        toast.error("Failed to end conversation");
      }
    } catch (error) {
      console.error("Error ending conversation:", error);
      toast.error("Error ending conversation");
    }
  };

  const handleSendMessage = async () => {
    if (!messageInput.trim() || !selectedConversation || isSending) return;

    setIsSending(true);
    const messageToSend = messageInput.trim();
    setMessageInput(""); // Clear immediately to prevent duplicate sends

    try {
      // Call API to send message via WhatsApp
      const result = await sendOperatorMessage(
        selectedConversation.conversation.conversation_id,
        selectedConversation.conversation.user_id,
        messageToSend,
        "operator_001"
      );

      if (result.success) {
        // Add message to UI
        appendMessageToSelectedConversation({
          timestamp: new Date().toISOString(),
          is_user: false,
          content: messageToSend,
          type: "text",
          handled_by: "human",
        });

        toast.success("Message sent to customer");
      } else {
        toast.error("Failed to send message");
      }
    } catch (error) {
      console.error("Error sending message:", error);
      toast.error("Error sending message");
    } finally {
      setIsSending(false);
    }
  };
  // Feedback handlers
  const handleFeedback = (message, feedbackType) => {
    if (feedbackType === "good") {
      // Submit positive feedback immediately
      submitFeedback({
        conversation_id: selectedConversation.conversation.conversation_id,
        message_id: message.id || `msg_${Date.now()}`,
        user_question: getPreviousUserMessage(message),
        bot_response: message.content,
        feedback_type: "good",
        language: selectedConversation.conversation.language,
      });
      toast.success("👍 Thanks for your feedback!");
    } else if (feedbackType === "wrong") {
      // Show modal to get correct answer
      setFeedbackModal({
        message,
        feedbackType,
      });
    } else if (feedbackType === "like") {
      // Show modal to edit question + answer and save to FAQ (4 languages)
      setFeedbackModal({
        message,
        feedbackType: "like",
      });
    }
  };

  const getPreviousUserMessage = (botMessage) => {
    const messages = selectedConversation.history;
    const botIndex = messages.findIndex((m) => m === botMessage);

    // Find the previous user message
    for (let i = botIndex - 1; i >= 0; i--) {
      if (messages[i].is_user) {
        return messages[i].content;
      }
    }

    return "Unknown question";
  };

  const submitCorrection = async (correctAnswer, feedbackReason) => {
    const result = await submitFeedback({
      conversation_id: selectedConversation.conversation.conversation_id,
      message_id: feedbackModal.message.id || `msg_${Date.now()}`,
      user_question: getPreviousUserMessage(feedbackModal.message),
      bot_response: feedbackModal.message.content,
      feedback_type: "wrong",
      correct_answer: correctAnswer,
      feedback_reason: feedbackReason,
      language: selectedConversation.conversation.language,
    });

    if (result.success) {
      setFeedbackModal(null);
    }
  };

  const submitLikeToFaq = async (editedQuestion, editedAnswer) => {
    const result = await submitFeedback({
      conversation_id: selectedConversation.conversation.conversation_id,
      message_id: feedbackModal.message.id || `msg_${Date.now()}`,
      user_question: editedQuestion,
      bot_response: feedbackModal.message.content,
      feedback_type: "save_to_faq",
      correct_answer: editedAnswer,
      language: selectedConversation.conversation.language,
    });

    if (result.success) {
      setFeedbackModal(null);
      toast.success("Saved to FAQ in 4 languages!");
    }
  };

  return (
    <div className="h-[calc(100vh-8rem)]">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-6"
      >
        <h1 className="text-4xl font-bold gradient-text font-display mb-2">
          Live Chat Monitoring
        </h1>
        <div className="flex items-center justify-between">
          <p className="text-xl text-slate-600">
            Monitor and manage live conversations in real-time
          </p>

          {/* Operator Status + Refresh Button */}
          <div className="flex items-center space-x-4">
            <select
              value={operatorStatus}
              onChange={(e) => setOperatorStatus(e.target.value)}
              className="input-field"
            >
              <option value="available">🟢 Available</option>
              <option value="busy">🟡 Busy</option>
              <option value="away">🔴 Away</option>
            </select>

            {/* ✅ Manual Refresh Button */}
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

            <div className="flex items-center space-x-2 text-sm">
              <SignalIcon className="w-4 h-4 text-green-500 animate-pulse" />
              <span className="text-slate-600">Live</span>
            </div>
          </div>
        </div>
      </motion.div>

      <div className="grid grid-cols-12 gap-6 h-[calc(100%-8rem)]">
        {/* Conversations List */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="col-span-3 space-y-4 h-full overflow-y-auto"
        >
          {/* Waiting Queue */}
          {waitingQueue.length > 0 && (
            <div className="card p-4">
              <h3 className="font-bold text-slate-800 mb-3 flex items-center">
                <HandRaisedIcon className="w-5 h-5 mr-2 text-orange-500" />
                Waiting Queue ({waitingQueue.length})
              </h3>
              <div className="space-y-2">
                {waitingQueue.map((item) => (
                  <div
                    key={item.conversation_id}
                    className="p-3 bg-orange-50 border border-orange-200 rounded-lg cursor-pointer hover:bg-orange-100 transition-colors"
                    onClick={() => {
                      const conv = activeConversations.find(
                        (c) =>
                          c.conversation_id === item.conversation_id &&
                          c.user_id === item.user_id
                      );
                      if (conv)
                        setSelectedConversation({
                          conversation: conv,
                          history: [],
                        });
                    }}
                  >
                    <div className="flex items-start justify-between mb-1">
                      <span className="font-medium text-slate-800 text-sm">
                        {item.user_name}
                      </span>
                      <SentimentIndicator sentiment={item.sentiment} />
                    </div>
                    <div className="flex items-center justify-between text-xs text-slate-600">
                      <span>
                        {Math.floor(item.wait_time_seconds / 60)}m waiting
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleTakeOver(item.conversation_id, item.user_id);
                        }}
                        className="text-orange-600 hover:text-orange-700 font-medium"
                      >
                        Take Over
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Active Conversations */}
          <div className="card p-4 flex-1 overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold text-slate-800 flex items-center">
                <ChatBubbleLeftRightIcon className="w-5 h-5 mr-2 text-primary-600" />
                Active Conversations ({activeConversations.length})
              </h3>
              {/* ✅ Auto-refresh indicator */}
              <span className="text-xs text-slate-500 flex items-center space-x-1">
                <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                <span>Auto-updating</span>
              </span>
              {isLoading && (
                <span className="text-xs text-slate-400">Loading...</span>
              )}
            </div>
            {/* ✅ Search by name or phone */}
            <div className="relative mb-3">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={liveSearchQuery}
                onChange={(e) => setLiveSearchQuery(e.target.value)}
                placeholder="Search by name or phone..."
                className="input-field w-full pl-9 pr-4 py-2 text-sm"
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
            <div className="space-y-2">
              {activeConversations.map((conv) => (
                <div
                  key={conv.conversation_id}
                  className={`p-3 rounded-lg cursor-pointer transition-all ${
                    selectedConversation?.conversation?.conversation_id ===
                    conv.conversation_id
                      ? "bg-primary-50 border-2 border-primary-300"
                      : "bg-slate-50 border border-slate-200 hover:bg-slate-100"
                  }`}
                  onClick={() => {
                    // ✅ PRIORITY: Show conversation immediately with loading state
                    setSelectedConversation({
                      conversation: conv,
                      history: [],
                    });
                    setMessagesLoading(true);
                  }}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2">
                        <p className="font-medium text-slate-800 text-sm">
                          {conv.user_name}
                        </p>
                        {/* ✅ "Live" Badge - currently chatting with AI */}
                        {conv.is_live && (
                          <span className="inline-block px-2 py-0.5 bg-green-500 text-white text-xs font-bold rounded-full">
                            Live
                          </span>
                        )}
                        {newConversationIds.has(conv.conversation_id) && (
                          <span className="inline-block px-2 py-0.5 bg-blue-500 text-white text-xs font-bold rounded-full animate-pulse">
                            New
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-500">
                        {conv.user_phone}
                      </p>
                    </div>
                    <SentimentIndicator sentiment={conv.sentiment} />
                  </div>

                  <div className="mb-2"><StatusBadge status={conv.status} /></div>

                  {conv.last_message && (
                    <p className="text-xs text-slate-600 truncate mb-1">
                      {conv.last_message.content}
                    </p>
                  )}

                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span>{conv.message_count} messages</span>
                    <span>{(conv.duration_seconds || 0) > 0 ? `${Math.floor(conv.duration_seconds / 60)}m` : ""}</span>
                  </div>
                </div>
              ))}
              {hasMoreChats && (
                <button
                  onClick={loadMoreChats}
                  disabled={loadingMoreChats}
                  className="w-full py-3 mt-2 text-sm font-medium text-primary-600 hover:bg-primary-50 rounded-lg border border-primary-200 transition"
                >
                  {loadingMoreChats ? "Loading..." : "Load More"}
                </button>
              )}
            </div>
          </div>
        </motion.div>

        {/* Chat Window */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="col-span-6 card flex flex-col h-full overflow-hidden"
        >
          {selectedConversation ? (
            <>
              {/* Chat Header - Fixed Height */}
              <div className="p-4 border-b border-slate-200 flex-shrink-0">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <div className="w-10 h-10 bg-gradient-to-r from-primary-400 to-secondary-400 rounded-full flex items-center justify-center text-white font-bold">
                      {selectedConversation.conversation.user_name.charAt(0)}
                    </div>
                    <div>
                      <p className="font-bold text-slate-800">
                        {selectedConversation.conversation.user_name}
                      </p>
                      <div className="flex items-center space-x-3 text-xs text-slate-500">
                        <span className="flex items-center">
                          <PhoneIcon className="w-3 h-3 mr-1" />
                          {selectedConversation.conversation.user_phone}
                        </span>
                        <span className="flex items-center">
                          <GlobeAltIcon className="w-3 h-3 mr-1" />
                          {selectedConversation.conversation.language.toUpperCase()}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2">
                    {selectedConversation.conversation.status === "bot" ? (
                      <button
                        onClick={() =>
                          handleTakeOver(
                            selectedConversation.conversation.conversation_id,
                            selectedConversation.conversation.user_id
                          )
                        }
                        className="btn-primary text-sm"
                      >
                        <HandRaisedIcon className="w-4 h-4 mr-1" />
                        Take Over
                      </button>
                    ) : (
                      selectedConversation.conversation.status === "human" && (
                        <button
                          onClick={() =>
                            handleReleaseToBot(
                              selectedConversation.conversation.conversation_id,
                              selectedConversation.conversation.user_id
                            )
                          }
                          className="btn-secondary text-sm"
                        >
                          <ArrowRightIcon className="w-4 h-4 mr-1" />
                          Release to Bot
                        </button>
                      )
                    )}
                    <StatusBadge status={selectedConversation.conversation.status} />

                    {/* ✅ Reload Messages Button */}
                    <button
                      onClick={reloadSelectedConversationMessages}
                      title="Reload conversation messages"
                      className="p-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 hover:text-slate-700 transition-all"
                    >
                      <svg
                        className="w-4 h-4"
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
                    </button>
                  </div>
                </div>
              </div>

              {/* Messages - Fixed Height with Internal Scroll */}
              <div
                ref={messagesContainerRef}
                className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0 flex flex-col"
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
                {messagesLoading && selectedConversation.history.length === 0 && (
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
                {selectedConversation.history.map((msg, index) => {
                  // ✅ Check if this is a voice message - Updated to use new Firebase structure
                  // First check msg.type (preferred), fallback to old content-based detection
                  const isVoiceMessage =
                    msg.type === "voice" ||
                    msg.content === "[رسالة صوتية]" ||
                    msg.content === "رسالة صوتية" ||
                    msg.audio_url;

                  // ✅ Check if this is an image message - Use new Firebase structure
                  const isImageMessage =
                    msg.type === "image" ||
                    msg.content === "[صورة]" ||
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
                          className={`rounded-2xl px-4 py-2 ${
                            msg.is_user
                              ? "bg-slate-100 text-slate-800"
                              : "bg-gradient-to-r from-primary-500 to-secondary-500 text-white"
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
                                    <span className="text-sm">رسالة صوتية</span>
                                    <span className="text-xs opacity-75">
                                      (URL not available)
                                    </span>
                                  </div>
                                )}
                              </div>
                            </div>
                          ) : (
                            <p className="text-sm">{msg.content}</p>
                          )}
                        </div>
                        <div className="flex items-center space-x-2 mt-1 px-2">
                          <span className="text-xs text-slate-400">
                            {formatMessageTime(msg.timestamp)}
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
                                  <div className="flex items-center space-x-1 ml-2">
                                    <button
                                      onClick={() =>
                                        handleFeedback(msg, "good")
                                      }
                                      className="text-xs hover:scale-125 transition-transform"
                                      title="Good response"
                                    >
                                      ��
                                    </button>
                                    <button
                                      onClick={() =>
                                        handleFeedback(msg, "wrong")
                                      }
                                      className="text-xs hover:scale-125 transition-transform"
                                      title="Wrong answer - train bot"
                                    >
                                      👎
                                    </button>
                                  </div>
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
                <div className="p-4 border-t border-slate-200 flex-shrink-0">
                  {selectedImage && (
                    <div className="mb-3 p-3 bg-slate-100 rounded-lg">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-3 min-w-0">
                          <img
                            src={selectedImage.preview}
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
                            className="btn-primary flex items-center space-x-1"
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
                            className="btn-primary flex items-center space-x-1 disabled:opacity-50"
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
                        onKeyPress={(e) =>
                          e.key === "Enter" && !isSending && handleSendMessage()
                        }
                        placeholder="Type your message..."
                        className="input-field flex-1"
                        disabled={isSending}
                      />
                      {/* Voice Recording Button */}
                      <button
                        onClick={startRecording}
                        className="p-3 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg transition-colors"
                        title="Record voice message"
                      >
                        <MicrophoneIcon className="w-5 h-5" />
                      </button>
                      <button
                        onClick={() => imageInputRef.current?.click()}
                        className="p-3 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg transition-colors"
                        title="Send image"
                      >
                        <PhotoIcon className="w-5 h-5" />
                      </button>
                      {/* Send Text Button */}
                      <button
                        onClick={handleSendMessage}
                        disabled={isSending || !messageInput.trim()}
                        className={`btn-primary disabled:opacity-50 ${
                          isSending ? "cursor-not-allowed" : ""
                        }`}
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
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-400">
              <div className="text-center">
                <ChatBubbleLeftRightIcon className="w-16 h-16 mx-auto mb-4 text-slate-300" />
                <p className="text-lg font-medium">
                  Select a conversation to view
                </p>
              </div>
            </div>
          )}
        </motion.div>

        {/* Conversation Details */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          className="col-span-3 space-y-4 h-full overflow-y-auto"
        >
          {selectedConversation ? (
            <>
              {/* User Info */}
              <div className="card p-4">
                <h3 className="font-bold text-slate-800 mb-3 flex items-center">
                  <UserIcon className="w-5 h-5 mr-2 text-primary-600" />
                  User Information
                </h3>
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-slate-500">Name</p>
                    <p className="font-medium text-slate-800">
                      {selectedConversation.conversation.user_name}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Phone</p>
                    <p className="font-medium text-slate-800">
                      {selectedConversation.conversation.user_phone}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Language</p>
                    <p className="font-medium text-slate-800">
                      {selectedConversation.conversation.language.toUpperCase()}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Gender</p>
                    <p className="font-medium text-slate-800 capitalize">
                      {selectedConversation.conversation.gender || "Unknown"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Sentiment</p>
                    <div className="flex items-center space-x-2">
                      <SentimentIndicator sentiment={selectedConversation.conversation.sentiment} />
                      <span className="font-medium text-slate-800 capitalize">
                        {selectedConversation.conversation.sentiment}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Conversation Stats */}
              <div className="card p-4">
                <h3 className="font-bold text-slate-800 mb-3 flex items-center">
                  <ChartBarIcon className="w-5 h-5 mr-2 text-secondary-600" />
                  Conversation Stats
                </h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Messages</span>
                    <span className="font-medium text-slate-800">
                      {selectedConversation.conversation.message_count}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Duration</span>
                    <span className="font-medium text-slate-800">
                      {Math.floor(
                        selectedConversation.conversation.duration_seconds / 60
                      )}
                      m{" "}
                      {selectedConversation.conversation.duration_seconds % 60}s
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-slate-600">Status</span>
                    <StatusBadge status={selectedConversation.conversation.status} />
                  </div>
                  {selectedConversation.conversation.operator_id && (
                    <div className="flex justify-between">
                      <span className="text-sm text-slate-600">Operator</span>
                      <span className="font-medium text-slate-800">
                        {selectedConversation.conversation.operator_id}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Quick Actions */}
              <div className="card p-4">
                <h3 className="font-bold text-slate-800 mb-3">Quick Actions</h3>
                <div className="space-y-2">
                  <button className="w-full btn-ghost text-left text-sm">
                    <UserGroupIcon className="w-4 h-4 mr-2" />
                    Transfer to Another Operator
                  </button>
                  <button className="w-full btn-ghost text-left text-sm">
                    <ExclamationCircleIcon className="w-4 h-4 mr-2" />
                    Mark as Priority
                  </button>
                  <button
                    onClick={() =>
                      handleEndConversation(
                        selectedConversation.conversation.conversation_id,
                        selectedConversation.conversation.user_id
                      )
                    }
                    className="w-full btn-ghost text-left text-sm text-red-600 hover:bg-red-50"
                  >
                    <XMarkIcon className="w-4 h-4 mr-2" />
                    End Conversation
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="card p-4">
              <p className="text-center text-slate-500">
                Select a conversation to view details
              </p>
            </div>
          )}
        </motion.div>
      </div>

      {/* Feedback Modals */}
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
          conversation={selectedConversation.conversation}
          onClose={() => setFeedbackModal(null)}
          onSubmit={submitCorrection}
        />
      )}
    </div>
  );
};

export default LiveChat;
