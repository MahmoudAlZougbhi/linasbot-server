import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChatBubbleLeftRightIcon,
  UserIcon,
  ClockIcon,
  PhoneIcon,
  GlobeAltIcon,
  HandRaisedIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  ArrowRightIcon,
  PaperAirplaneIcon,
  UserGroupIcon,
  SignalIcon,
  XMarkIcon,
  ChartBarIcon,
  MicrophoneIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { useApi } from "../hooks/useApi";
import { formatMessageTime, formatDuration } from "../utils/dateUtils";
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
            : "bg-white bg-opacity-20 hover:bg-opacity-40 text-white"
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
          className="w-full h-1 bg-white bg-opacity-30 rounded-full appearance-none cursor-pointer accent-white"
          style={{
            background: `linear-gradient(to right, white ${
              (currentTime / duration) * 100
            }%, rgba(255,255,255,0.3) ${(currentTime / duration) * 100}%)`,
          }}
        />
        <div className="text-xs text-white font-medium">
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

const LiveChat = () => {
  const [activeConversations, setActiveConversations] = useState([]);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [waitingQueue, setWaitingQueue] = useState([]);
  const [messageInput, setMessageInput] = useState("");
  const [operatorStatus, setOperatorStatus] = useState("available");
  const [isLoading, setIsLoading] = useState(true);
  const [useMockData, setUseMockData] = useState(false);
  const [feedbackModal, setFeedbackModal] = useState(null);

  // ✅ Voice recording state for operator
  const [isRecording, setIsRecording] = useState(false);
  const [recordedAudio, setRecordedAudio] = useState(null);
  const [recordingTime, setRecordingTime] = useState(0);

  // ✅ Image Upload State
  const [selectedImage, setSelectedImage] = useState(null);
  const imageInputRef = useRef(null);

  // ✅ Auto-refresh state (Solution 1 + 4: Smart refresh with badges)
  const [lastRefreshTime, setLastRefreshTime] = useState(new Date());
  const [newConversationIds, setNewConversationIds] = useState(new Set()); // Track new conversations
  const [isRefreshing, setIsRefreshing] = useState(false);

  // ✅ Send button race condition state
  const [isSending, setIsSending] = useState(false);

  // ✅ Messages loading state for lazy loading
  const [messagesLoading, setMessagesLoading] = useState(false);

  const messagesEndRef = useRef(null);
  const selectedConversationRef = useRef(null);
  const activeConversationsRef = useRef([]); // ✅ Ref to track current conversations (fixes stale closure)
  const useMockDataRef = useRef(false); // ✅ Ref to track mock data status (fixes stale closure)
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

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

  const {
    getLiveConversations,
    getWaitingQueue,
    takeoverConversation,
    releaseConversation,
    sendOperatorMessage,
    updateOperatorStatus,
    submitFeedback,
  } = useApi();

  // Fetch conversation messages with timeout
  const fetchConversationMessages = async (userId, conversationId) => {
    // Create AbortController for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout

    try {
      // Use the same base URL logic as useApi
      const baseURL =
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1"
          ? "http://localhost:8003"
          : window.location.origin;

      console.log(
        `Fetching messages for user ${userId}, conversation ${conversationId}`
      );
      const response = await fetch(
        `${baseURL}/api/live-chat/conversation/${userId}/${conversationId}`,
        { signal: controller.signal }
      );
      clearTimeout(timeoutId);

      const data = await response.json();

      console.log("API Response:", data);

      if (data.success && data.messages) {
        console.log(`Loaded ${data.messages.length} messages (${data.returned_messages || data.messages.length} of ${data.total_messages || data.messages.length} total)`);
        return data.messages;
      }
      console.warn("No messages found or API error:", data);
      return [];
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        console.error("Message fetch timed out after 60 seconds");
        toast.error("Loading messages timed out - conversation may have too many messages");
      } else {
        console.error("Error fetching conversation messages:", error);
      }
      return [];
    }
  };

  // Fetch real data from API
  useEffect(() => {
    const fetchLiveData = async () => {
      // Only show loading on initial load, not on refresh
      if (!activeConversations.length) {
        setIsLoading(true);
      }

      try {
        // Fetch active conversations
        const conversationsResponse = await getLiveConversations();

        if (
          conversationsResponse.success &&
          conversationsResponse.conversations
        ) {
          // ✅ PRIORITY: Display chats immediately without waiting for messages
          setActiveConversations(conversationsResponse.conversations);
          setUseMockData(false);

          // Use ref to check current selection (avoids stale closure)
          const currentSelection = selectedConversationRef.current;

          // Only select first conversation if none selected AND it's the initial load
          if (
            !currentSelection &&
            conversationsResponse.conversations.length > 0 &&
            !activeConversations.length
          ) {
            const firstConv = conversationsResponse.conversations[0];
            // ✅ Set conversation immediately with empty history (show loading state)
            setSelectedConversation({
              conversation: firstConv,
              history: [],
            });
            // ✅ Lazy load messages asynchronously - don't block UI
            setMessagesLoading(true);
            fetchConversationMessages(
              firstConv.user_id,
              firstConv.conversation_id
            ).then((messages) => {
              setSelectedConversation((prev) =>
                prev?.conversation?.conversation_id === firstConv.conversation_id
                  ? { ...prev, history: messages }
                  : prev
              );
              setMessagesLoading(false);
            });
          } else if (currentSelection) {
            // If a conversation is selected, update its data but keep it selected
            const updatedConv = conversationsResponse.conversations.find(
              (c) =>
                c.conversation_id ===
                currentSelection.conversation.conversation_id
            );
            if (updatedConv) {
              // Update the conversation data but keep the same history
              setSelectedConversation((prev) => ({
                ...prev,
                conversation: updatedConv,
              }));
            }
          }
        } else {
          // Backend offline - use mock data
          if (!activeConversations.length) {
            loadMockData();
          }
        }

        // Fetch waiting queue
        const queueResponse = await getWaitingQueue();
        if (queueResponse.success && queueResponse.queue) {
          setWaitingQueue(queueResponse.queue);
        }
      } catch (error) {
        console.error("Error fetching live chat data:", error);
        if (!activeConversations.length) {
          loadMockData();
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchLiveData();

    // ============================================================
    // 📡 SSE (Server-Sent Events) for Real-Time Updates
    // Replaces polling with efficient server-push notifications
    // ============================================================
    let eventSource = null;
    let reconnectTimeout = null;
    let fallbackInterval = null;

    const connectSSE = () => {
      // Skip SSE if using mock data
      if (useMockDataRef.current) return;

      const baseURL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? 'http://localhost:8003'
        : '';

      try {
        eventSource = new EventSource(`${baseURL}/api/live-chat/events`);

        eventSource.onopen = () => {
          console.log('📡 SSE connected - real-time updates enabled');
          // Clear fallback polling when SSE connects
          if (fallbackInterval) {
            clearInterval(fallbackInterval);
            fallbackInterval = null;
          }
        };

        // Handle conversation list updates
        eventSource.addEventListener('conversations', (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.conversations) {
              const previousIds = new Set(
                activeConversationsRef.current.map((c) => c.conversation_id)
              );
              const newIds = new Set(
                data.conversations
                  .filter((c) => !previousIds.has(c.conversation_id))
                  .map((c) => c.conversation_id)
              );

              setActiveConversations(data.conversations);
              setNewConversationIds(newIds);
              setLastRefreshTime(new Date());

              if (newIds.size > 0) {
                setTimeout(() => setNewConversationIds(new Set()), 10000);
              }
            }
          } catch (e) {
            console.error('SSE parse error:', e);
          }
        });

        // Handle new message events
        eventSource.addEventListener('new_message', async (event) => {
          try {
            const data = JSON.parse(event.data);
            console.log('📨 SSE: New message received', data);

            // Refresh conversation list to update last message preview
            setIsRefreshing(true);
            const conversationsResponse = await getLiveConversations();
            if (conversationsResponse.success && conversationsResponse.conversations) {
              setActiveConversations(conversationsResponse.conversations);
              setLastRefreshTime(new Date());
            }
            setIsRefreshing(false);

            // If this message is for the currently selected conversation, fetch new messages
            const currentSelection = selectedConversationRef.current;
            if (currentSelection &&
                (currentSelection.conversation.user_id === data.user_id ||
                 currentSelection.conversation.conversation_id === data.conversation_id)) {
              const messages = await fetchConversationMessages(
                currentSelection.conversation.user_id,
                currentSelection.conversation.conversation_id
              );
              if (messages && messages.length > 0) {
                setSelectedConversation((prev) => {
                  if (!prev) return prev;
                  return { ...prev, history: messages };
                });
              }
            }
          } catch (e) {
            console.error('SSE new_message error:', e);
          }
        });

        // Handle new conversation events
        eventSource.addEventListener('new_conversation', async (event) => {
          try {
            const data = JSON.parse(event.data);
            console.log('📡 SSE: New conversation', data);

            // Refresh conversation list
            const conversationsResponse = await getLiveConversations();
            if (conversationsResponse.success && conversationsResponse.conversations) {
              const newIds = new Set([data.conversation_id]);
              setActiveConversations(conversationsResponse.conversations);
              setNewConversationIds(newIds);
              setLastRefreshTime(new Date());

              setTimeout(() => setNewConversationIds(new Set()), 10000);
            }
          } catch (e) {
            console.error('SSE new_conversation error:', e);
          }
        });

        // Handle heartbeat (keep-alive)
        eventSource.addEventListener('heartbeat', () => {
          // Connection is alive, nothing to do
        });

        eventSource.onerror = (error) => {
          console.warn('📡 SSE connection error, falling back to polling');
          eventSource.close();

          // Start fallback polling
          if (!fallbackInterval) {
            fallbackInterval = setInterval(async () => {
              if (useMockDataRef.current) return;
              try {
                const conversationsResponse = await getLiveConversations();
                if (conversationsResponse.success && conversationsResponse.conversations) {
                  setActiveConversations(conversationsResponse.conversations);
                  setLastRefreshTime(new Date());
                }
              } catch (e) {
                // Silent fail
              }
            }, 10000); // Slower fallback polling (10s)
          }

          // Try to reconnect SSE after 5 seconds
          reconnectTimeout = setTimeout(connectSSE, 5000);
        };

      } catch (error) {
        console.error('SSE initialization error:', error);
      }
    };

    // Start SSE connection
    connectSSE();

    // Cleanup on unmount
    return () => {
      if (eventSource) {
        eventSource.close();
      }
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      if (fallbackInterval) {
        clearInterval(fallbackInterval);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty dependency array - only run once on mount

  // ✅ Fetch messages when selected conversation changes (not polling)
  useEffect(() => {
    // Skip for mock data
    if (!selectedConversation || useMockData) return;

    // Fetch messages once when conversation is selected
    const fetchMessages = async () => {
      try {
        const messages = await fetchConversationMessages(
          selectedConversation.conversation.user_id,
          selectedConversation.conversation.conversation_id
        );
        if (messages && messages.length > 0) {
          setSelectedConversation((prev) => {
            if (!prev) return prev;
            return { ...prev, history: messages };
          });
        }
      } catch (error) {
        // Silent fail
      }
    };

    fetchMessages();
  }, [selectedConversation?.conversation?.conversation_id, useMockData]); // Only fetch when conversation changes

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

  // ✅ Manual refresh handler - allows admin to immediately refresh conversation list
  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    try {
      const conversationsResponse = await getLiveConversations();
      if (
        conversationsResponse.success &&
        conversationsResponse.conversations
      ) {
        // ✅ Use ref to get current state (fixes stale closure issue)
        const previousIds = new Set(
          activeConversationsRef.current.map((c) => c.conversation_id)
        );
        const newIds = new Set(
          conversationsResponse.conversations
            .filter((c) => !previousIds.has(c.conversation_id))
            .map((c) => c.conversation_id)
        );

        setActiveConversations(conversationsResponse.conversations);
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

  // ✅ Reload messages for currently selected conversation
  // Useful when admin wants to see latest messages without clicking away and back
  const reloadSelectedConversationMessages = async () => {
    if (!selectedConversation) return;

    try {
      console.log(
        `Reloading messages for conversation ${selectedConversation.conversation.conversation_id}`
      );
      const messages = await fetchConversationMessages(
        selectedConversation.conversation.user_id,
        selectedConversation.conversation.conversation_id
      );
      setSelectedConversation((prev) => ({
        ...prev,
        history: messages,
      }));
      toast.success(`Loaded ${messages.length} messages`);
    } catch (error) {
      console.error("Error reloading conversation messages:", error);
      toast.error("Failed to reload messages");
    }
  };

  // Auto-scroll to bottom of messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [selectedConversation]);

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
      const baseURL =
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1"
          ? "http://localhost:8003"
          : window.location.origin;

      const response = await fetch(
        `${baseURL}/api/live-chat/end-conversation`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            conversation_id: conversationId,
            user_id: userId,
            operator_id: "operator_001",
          }),
        }
      );

      const result = await response.json();

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
        const newMessage = {
          timestamp: new Date().toISOString(),
          is_user: false,
          content: messageToSend,
          type: "text",
          handled_by: "human",
        };

        setSelectedConversation((prev) => ({
          ...prev,
          history: [...prev.history, newMessage],
        }));

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



  // ✅ Voice Recording Handlers
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];

      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/webm",
        });
        const audioUrl = URL.createObjectURL(audioBlob);
        setRecordedAudio({ blob: audioBlob, url: audioUrl });
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingTime(0);

      // Timer for recording duration
      const interval = setInterval(() => {
        setRecordingTime((prev) => {
          if (prev >= 300) {
            // 5 minutes max
            stopRecording();
            clearInterval(interval);
            return prev;
          }
          return prev + 1;
        });
      }, 1000);
    } catch (error) {
      console.error("Error accessing microphone:", error);
      toast.error("Could not access microphone");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream
        .getTracks()
        .forEach((track) => track.stop());
      setIsRecording(false);
    }
  };

  const discardRecording = () => {
    setRecordedAudio(null);
    setRecordingTime(0);
  };

  const sendVoiceMessage = async () => {
    if (!recordedAudio || !selectedConversation) return;

    try {
      // Convert blob to base64
      const reader = new FileReader();
      reader.onload = async () => {
        const base64Audio = reader.result.split(",")[1];

        // Call API to send voice message
        const result = await sendOperatorMessage(
          selectedConversation.conversation.conversation_id,
          selectedConversation.conversation.user_id,
          base64Audio,
          "operator_001",
          "voice"
        );

        if (result.success) {
          // Add voice message to UI
          const newMessage = {
            timestamp: new Date().toISOString(),
            is_user: false,
            content: "[رسالة صوتية]",
            type: "voice",
            audio_url: recordedAudio.url,
            handled_by: "human",
          };

          setSelectedConversation((prev) => ({
            ...prev,
            history: [...prev.history, newMessage],
          }));

          setRecordedAudio(null);
          setRecordingTime(0);
          toast.success("Voice message sent to customer");
        } else {
          toast.error("Failed to send voice message");
        }
      };
      reader.readAsDataURL(recordedAudio.blob);
    } catch (error) {
      console.error("Error sending voice message:", error);
      toast.error("Error sending voice message");
    }
  };

  const formatRecordingTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  // ✅ Image Upload Handlers
  const handleImageSelect = (event) => {
    const file = event.target.files?.[0];
    if (file && file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (e) => {
        setSelectedImage({
          file: file,
          preview: e.target?.result,
          name: file.name,
        });
      };
      reader.readAsDataURL(file);
    } else {
      toast.error("Please select a valid image file");
    }
  };

  const discardImage = () => {
    setSelectedImage(null);
    if (imageInputRef.current) {
      imageInputRef.current.value = "";
    }
  };

  const sendImageMessage = async () => {
    if (!selectedImage || !selectedConversation) return;

    try {
      // Convert to base64
      const base64Image = selectedImage.preview.split(",")[1];

      // Call API to send image message
      const result = await sendOperatorMessage(
        selectedConversation.conversation.conversation_id,
        selectedConversation.conversation.user_id,
        base64Image,
        "operator_001",
        "image"
      );

      if (result.success) {
        // Add image message to UI
        const newMessage = {
          timestamp: new Date().toISOString(),
          is_user: false,
          content: "[صورة]",
          type: "image",
          image_url: selectedImage.preview,
          handled_by: "human",
        };

        setSelectedConversation((prev) => ({
          ...prev,
          history: [...prev.history, newMessage],
        }));

        discardImage();
        toast.success("Image sent to customer");
      } else {
        toast.error("Failed to send image");
      }
    } catch (error) {
      console.error("Error sending image:", error);
      toast.error("Error sending image");
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

  const getStatusBadge = (status) => {
    const badges = {
      bot: {
        color: "bg-blue-100 text-blue-700",
        icon: CheckCircleIcon,
        text: "Bot Handling",
      },
      human: {
        color: "bg-green-100 text-green-700",
        icon: UserIcon,
        text: "Human Handling",
      },
      waiting_human: {
        color: "bg-orange-100 text-orange-700",
        icon: ClockIcon,
        text: "Waiting",
      },
      resolved: {
        color: "bg-slate-100 text-slate-700",
        icon: CheckCircleIcon,
        text: "Resolved",
      },
    };

    const badge = badges[status] || badges.bot;
    const Icon = badge.icon;

    return (
      <span
        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badge.color}`}
      >
        <Icon className="w-3 h-3 mr-1" />
        {badge.text}
      </span>
    );
  };

  const getSentimentIndicator = (sentiment) => {
    const indicators = {
      positive: { color: "text-green-500", emoji: "😊" },
      neutral: { color: "text-slate-500", emoji: "😐" },
      negative: { color: "text-red-500", emoji: "😟" },
    };

    const indicator = indicators[sentiment] || indicators.neutral;

    return (
      <span className={`text-lg ${indicator.color}`} title={sentiment}>
        {indicator.emoji}
      </span>
    );
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
                        (c) => c.conversation_id === item.conversation_id
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
                      {getSentimentIndicator(item.sentiment)}
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
                    // ✅ Lazy load messages asynchronously - don't block UI
                    setMessagesLoading(true);
                    fetchConversationMessages(
                      conv.user_id,
                      conv.conversation_id
                    ).then((messages) => {
                      // Only update if this conversation is still selected
                      setSelectedConversation((prev) =>
                        prev?.conversation?.conversation_id === conv.conversation_id
                          ? { ...prev, history: messages }
                          : prev
                      );
                      setMessagesLoading(false);
                    });
                  }}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2">
                        <p className="font-medium text-slate-800 text-sm">
                          {conv.user_name}
                        </p>
                        {/* ✅ "New" Badge - shows for newly appeared conversations */}
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
                    {getSentimentIndicator(conv.sentiment)}
                  </div>

                  <div className="mb-2">{getStatusBadge(conv.status)}</div>

                  {conv.last_message && (
                    <p className="text-xs text-slate-600 truncate mb-1">
                      {conv.last_message.content}
                    </p>
                  )}

                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span>{conv.message_count} messages</span>
                    <span>{Math.floor(conv.duration_seconds / 60)}m</span>
                  </div>
                </div>
              ))}
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
                    {getStatusBadge(selectedConversation.conversation.status)}

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
              <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
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
                    <motion.div
                      key={index}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: index * 0.05 }}
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
                                {msg.handled_by === "bot"
                                  ? "🤖 Bot"
                                  : "👤 Human"}
                              </span>
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
                    </motion.div>
                  );
                })}
                <div ref={messagesEndRef} />
              </div>

              {/* Message Input - Fixed Height - Text + Voice */}
              {selectedConversation.conversation.status === "human" && (
                <div className="p-4 border-t border-slate-200 flex-shrink-0">
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
                            className="btn-primary flex items-center space-x-1"
                          >
                            <PaperAirplaneIcon className="w-4 h-4" />
                            <span>Send</span>
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
                      {getSentimentIndicator(
                        selectedConversation.conversation.sentiment
                      )}
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
                    {getStatusBadge(selectedConversation.conversation.status)}
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

      {/* Feedback Modal */}
      {feedbackModal && (
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
