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
  XMarkIcon,
  ChartBarIcon,
  MicrophoneIcon,
  PhotoIcon,
  MagnifyingGlassIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from "@heroicons/react/24/outline";
import { useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import { useApi } from "../hooks/useApi";
import { useOperatorStatus } from "../contexts/OperatorStatusContext";
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
  editLiveChatMessage,
  fetchFaqMatchContext,
  faqUpdateAnswer,
  faqCreateFromLivechat,
} from "../utils/liveChatApi";

const LiveChat = () => {
  const [searchParams] = useSearchParams();
  const [activeConversations, setActiveConversations] = useState([]);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [waitingQueue, setWaitingQueue] = useState([]);
  const [messageInput, setMessageInput] = useState("");
  const { operatorStatus } = useOperatorStatus();
  const [isLoading, setIsLoading] = useState(true);
  const [useMockData, setUseMockData] = useState(false);
  const [feedbackModal, setFeedbackModal] = useState(null);
  const [editMessageModal, setEditMessageModal] = useState(null);
  const [faqCorrectionModal, setFaqCorrectionModal] = useState(null);

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
  const waitingSearchTerm = debouncedSearch.trim().toLowerCase();
  // Keep list page moderate to reduce backend/index reads per refresh.
  const CHAT_LIST_PAGE_SIZE = 30;
  const [chatPage, setChatPage] = useState(1);
  const [hasMoreChats, setHasMoreChats] = useState(false);
  const [loadingMoreChats, setLoadingMoreChats] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [botPanelOpen, setBotPanelOpen] = useState(false); // With bot floating panel when sidebar collapsed

  const MESSAGE_CACHE_TTL_MS = 5 * 60 * 1000; // 5 min - avoid refetch when switching back to same conv

  // Split handover: 1) waiting (no operator yet) 2) with operator (handover done, chatting)
  const userRequestedReasons = React.useMemo(
    () => ["user_request", "customer_requested_human"],
    []
  );

  const normalizeConversationStatus = React.useCallback((status, conversationState) => {
    const raw = String(status || conversationState || "").toLowerCase();
    if (["human", "assigned_to_operator", "assigned"].includes(raw)) return "human";
    if (["waiting_human", "waiting_for_operator", "waiting", "pending"].includes(raw)) {
      return "waiting_human";
    }
    if (["closed", "resolved", "archived"].includes(raw)) return "closed";
    return "bot";
  }, []);

  const normalizeIncomingConversation = React.useCallback((conv) => {
    if (!conv || typeof conv !== "object") return conv;
    const normalizedStatus = normalizeConversationStatus(
      conv.status,
      conv.conversation_state
    );
    const lastActivity = conv.last_activity || conv.last_message_at || null;
    const hasLastMessageObject = conv.last_message && typeof conv.last_message === "object";
    const normalizedLastMessage = hasLastMessageObject
      ? conv.last_message
      : (conv.last_message_text || conv.last_message)
        ? {
            content: conv.last_message_text ?? conv.last_message ?? "",
            timestamp: lastActivity,
            is_user: false,
          }
        : null;

    return {
      ...conv,
      status: normalizedStatus,
      user_phone: conv.user_phone || conv.phone_number || "",
      last_activity: lastActivity,
      last_message: normalizedLastMessage,
    };
  }, [normalizeConversationStatus]);

  const mergeActiveWaitingIntoQueue = (queue, activeList) => {
    const activeWaiting = (activeList || []).filter((conv) => conv.status === "waiting_human");
    if (!activeWaiting.length) return queue ?? [];
    const queueKeys = new Set(
      (queue || []).map((item) => `${item.user_id}_${item.conversation_id}`)
    );
    const merged = [...(queue || [])];
    activeWaiting.forEach((conv) => {
      const key = `${conv.user_id}_${conv.conversation_id}`;
      if (queueKeys.has(key)) return;
      merged.push({
        conversation_id: conv.conversation_id,
        user_id: conv.user_id,
        user_name: conv.user_name,
        user_phone: conv.user_phone,
        wait_time_seconds: 0,
        message_count: conv.message_count || 0,
        last_message: conv.last_message?.content ?? conv.last_message ?? "",
        reason: "user_request",
        sentiment: conv.sentiment || "neutral",
        language: conv.language || "ar",
      });
    });
    return merged;
  };

  const mergeMissingActiveChats = React.useCallback((incoming, existing) => {
    if (!Array.isArray(incoming)) return incoming || [];
    const existingList = existing || [];
    const keep = existingList.filter((conv) => ["human", "waiting_human"].includes(conv.status));
    if (!keep.length) return incoming;
    const incomingKeys = new Set(incoming.map((conv) => `${conv.user_id}_${conv.conversation_id}`));
    const missing = keep.filter((conv) => !incomingKeys.has(`${conv.user_id}_${conv.conversation_id}`));
    if (!missing.length) return incoming;
    return [...missing, ...incoming];
  }, []);

  const applyServerConversations = React.useCallback((incoming) => {
    if (!Array.isArray(incoming)) return;
    const normalizedIncoming = incoming.map(normalizeIncomingConversation).filter(Boolean);
    if (normalizedIncoming.length === 0) {
      if (activeConversationsRef.current?.length || cachedActiveConversationsRef.current?.length) {
        return;
      }
    }
    const baseline = activeConversationsRef.current?.length
      ? activeConversationsRef.current
      : cachedActiveConversationsRef.current;
    const merged = mergeMissingActiveChats(normalizedIncoming, baseline);
    setActiveConversations(merged);
  }, [mergeMissingActiveChats, normalizeIncomingConversation]);

  const effectiveWaitingQueue = React.useMemo(
    () => mergeActiveWaitingIntoQueue(waitingQueue, activeConversations),
    [waitingQueue, activeConversations]
  );

  const filteredWaitingQueue = React.useMemo(() => {
    if (!waitingSearchTerm) return effectiveWaitingQueue;
    return effectiveWaitingQueue.filter((item) => {
      const name = (item.user_name || "").toLowerCase();
      const phone = (item.user_phone || "").toLowerCase();
      return name.includes(waitingSearchTerm) || phone.includes(waitingSearchTerm);
    });
  }, [effectiveWaitingQueue, waitingSearchTerm]);

  const aiInitiatedHandover = React.useMemo(
    () => filteredWaitingQueue.filter((item) => !userRequestedReasons.includes((item.reason || "").toLowerCase())),
    [filteredWaitingQueue, userRequestedReasons]
  );
  const userRequestedHandover = React.useMemo(
    () => filteredWaitingQueue.filter((item) => userRequestedReasons.includes((item.reason || "").toLowerCase())),
    [filteredWaitingQueue, userRequestedReasons]
  );
  // Conversations where handover was done and we're talking with them (operator assigned)
  const withOperator = React.useMemo(
    () =>
      activeConversations.filter((c) => {
        if (c.status !== "human") return false;
        // Some records can temporarily miss operator_id while still being assigned to a human.
        return true;
      }),
    [activeConversations]
  );

  const filteredWithOperator = React.useMemo(() => {
    if (!waitingSearchTerm) return withOperator;
    return withOperator.filter((conv) => {
      const name = (conv.user_name || "").toLowerCase();
      const phone = (conv.user_phone || "").toLowerCase();
      return name.includes(waitingSearchTerm) || phone.includes(waitingSearchTerm);
    });
  }, [withOperator, waitingSearchTerm]);
  // Only bot conversations (exclude waiting_human + with operator) - shown below, release to bot moves here
  const botConversations = React.useMemo(
    () => activeConversations.filter((c) => c.status === "bot"),
    [activeConversations]
  );

  const liveBotConversations = React.useMemo(() => {
    const now = Date.now();
    const getLastTs = (conv) => {
      const ts = conv.last_activity || conv.last_message?.timestamp;
      return ts ? new Date(ts).getTime() : 0;
    };
    const enriched = botConversations.map((conv) => {
      const lastTs = getLastTs(conv);
      const isRecent = lastTs > 0 && now - lastTs <= 15 * 60 * 1000;
      return { ...conv, _lastTs: lastTs, _isLive: conv.is_live || isRecent };
    });
    return enriched
      .filter((conv) => conv._isLive)
      .sort((a, b) => b._lastTs - a._lastTs);
  }, [botConversations]);

  const historyBotConversations = React.useMemo(() => {
    const now = Date.now();
    const getLastTs = (conv) => {
      const ts = conv.last_activity || conv.last_message?.timestamp;
      return ts ? new Date(ts).getTime() : 0;
    };
    return botConversations
      .map((conv) => {
        const lastTs = getLastTs(conv);
        const isRecent = lastTs > 0 && now - lastTs <= 15 * 60 * 1000;
        return { ...conv, _lastTs: lastTs, _isLive: conv.is_live || isRecent };
      })
      .filter((conv) => !conv._isLive)
      .sort((a, b) => b._lastTs - a._lastTs);
  }, [botConversations]);

  // Read count per waiting conversation for unread badge: key = `${user_id}_${conversation_id}`
  const [readMessageCountByConv, setReadMessageCountByConv] = useState({});
  const markWaitingConversationRead = (userId, conversationId, messageCount) => {
    const key = `${userId}_${conversationId}`;
    setReadMessageCountByConv((prev) => ({ ...prev, [key]: messageCount }));
  };

  // Merge selected conversation into waiting queue when refetching so it doesn't disappear from the list
  const mergeSelectedIntoWaitingQueue = (newQueue, selectedRef) => {
    const selected = selectedRef?.current;
    if (!selected?.conversation || selected.conversation.status !== "waiting_human") return newQueue ?? [];
    const c = selected.conversation;
    const inQueue = (newQueue ?? []).some((q) => q.conversation_id === c.conversation_id && q.user_id === c.user_id);
    if (inQueue) return newQueue ?? [];
    const synthetic = {
      conversation_id: c.conversation_id,
      user_id: c.user_id,
      user_name: c.user_name,
      user_phone: c.user_phone,
      wait_time_seconds: 0,
      message_count: c.message_count || 0,
      last_message: c.last_message?.content ?? "",
      reason: "user_request",
      sentiment: c.sentiment || "neutral",
    };
    return [synthetic, ...(newQueue ?? [])];
  };

  const applyWaitingQueue = (queueResponse) => {
    const incoming = queueResponse?.queue;
    if (!Array.isArray(incoming)) return;
    if (incoming.length === 0) {
      if (waitingQueueRef.current?.length || cachedWaitingQueueRef.current?.length) {
        return;
      }
    }
    setWaitingQueue(mergeSelectedIntoWaitingQueue(incoming, selectedConversationRef));
  };

  const messagesContainerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const selectedConversationRef = useRef(null);
  const activeConversationsRef = useRef([]); // ✅ Ref to track current conversations (fixes stale closure)
  const waitingQueueRef = useRef([]);
  const cachedActiveConversationsRef = useRef([]);
  const cachedWaitingQueueRef = useRef([]);
  const useMockDataRef = useRef(false); // ✅ Ref to track mock data status (fixes stale closure)
  const debouncedSearchRef = useRef("");
  const isMountedRef = useRef(true); // ✅ Prevent setState after unmount (fixes slow-down on repeated opens)
  const previousConversationIdRef = useRef(null);
  const previousMessageCountRef = useRef(0);
  const messageCacheRef = useRef(new Map());
  const hasMoreMessagesRef = useRef(true);
  const autoLoadedPagesRef = useRef(1);
  const botListRef = useRef(null);

  // Keep refs in sync with state
  useEffect(() => {
    selectedConversationRef.current = selectedConversation;
  }, [selectedConversation]);

  useEffect(() => {
    hasMoreMessagesRef.current = hasMoreMessages;
  }, [hasMoreMessages]);

  useEffect(() => {
    activeConversationsRef.current = activeConversations;
    if (activeConversations?.length) {
      cachedActiveConversationsRef.current = activeConversations;
    }
  }, [activeConversations]);

  useEffect(() => {
    waitingQueueRef.current = waitingQueue;
    if (waitingQueue?.length) {
      cachedWaitingQueueRef.current = waitingQueue;
    }
  }, [waitingQueue]);

  useEffect(() => {
    try {
      sessionStorage.setItem(
        "liveChatActiveConversations",
        JSON.stringify(activeConversations || [])
      );
    } catch (err) {
      console.warn("LiveChat cache write error (active)", err);
    }
  }, [activeConversations]);

  useEffect(() => {
    try {
      sessionStorage.setItem(
        "liveChatWaitingQueue",
        JSON.stringify(waitingQueue || [])
      );
    } catch (err) {
      console.warn("LiveChat cache write error (waiting)", err);
    }
  }, [waitingQueue]);

  useEffect(() => {
    useMockDataRef.current = useMockData;
  }, [useMockData]);

  // Track mount state to avoid setState after unmount (fixes slowdown on repeated open/close)
  useEffect(() => {
    isMountedRef.current = true;
    const cachedChats = sessionStorage.getItem("liveChatActiveConversations");
    const cachedQueue = sessionStorage.getItem("liveChatWaitingQueue");
    if (cachedChats) {
      try {
        const parsed = JSON.parse(cachedChats);
        if (Array.isArray(parsed) && parsed.length > 0) {
          const normalized = parsed.map(normalizeIncomingConversation).filter(Boolean);
          setActiveConversations(normalized);
          activeConversationsRef.current = normalized;
          cachedActiveConversationsRef.current = normalized;
        }
      } catch (err) {
        console.warn("LiveChat cache parse error (active conversations)", err);
      }
    }
    if (cachedQueue) {
      try {
        const parsed = JSON.parse(cachedQueue);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setWaitingQueue(parsed);
          waitingQueueRef.current = parsed;
          cachedWaitingQueueRef.current = parsed;
        }
      } catch (err) {
        console.warn("LiveChat cache parse error (waiting queue)", err);
      }
    }
    return () => {
      isMountedRef.current = false;
      try {
        sessionStorage.setItem("liveChatActiveConversations", JSON.stringify(activeConversationsRef.current || []));
        sessionStorage.setItem("liveChatWaitingQueue", JSON.stringify(waitingQueueRef.current || []));
      } catch (err) {
        console.warn("LiveChat cache write error", err);
      }
    };
  }, [normalizeIncomingConversation]);

  // Debounce search input (250ms) - WhatsApp-style snappy
  useEffect(() => {
    const timer = setTimeout(() => {
      const trimmed = liveSearchQuery.trim();
      setDebouncedSearch(trimmed);
      debouncedSearchRef.current = trimmed;
    }, 250);
    return () => clearTimeout(timer);
  }, [liveSearchQuery]);

  useEffect(() => {
    const query = (searchParams.get("search") || "").trim();
    setLiveSearchQuery((prev) => (prev === query ? prev : query));
  }, [searchParams]);

  const {
    getUnifiedChats,
    getLiveConversations,
    getWaitingQueue,
    getConversationMessages,
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

  // Fetch conversation messages: use same axios as list (getUnifiedChats) so request hits same origin
  const fetchConversationMessages = React.useCallback(
    (userId, conversationId, days = 0, before = null, day_window = 0, limit = 50) =>
      getConversationMessages(userId, conversationId, days, before, day_window, limit),
    [getConversationMessages]
  );

  const SESSION_RECENT_OP_KEY = "live_chat_recent_op";
  const RECENT_OP_TTL_MS = 120000;

  const getRecentOpFromSession = React.useCallback((cacheKey) => {
    try {
      const raw = sessionStorage.getItem(SESSION_RECENT_OP_KEY);
      if (!raw) return [];
      const arr = JSON.parse(raw) || [];
      const now = Date.now();
      const parts = (cacheKey || "").split("_");
      const altKey = parts.length >= 2
        ? `${parts[0].startsWith("+") ? parts[0].slice(1) : `+${parts[0]}`}_${parts.slice(1).join("_")}`
        : "";
      return arr.filter((e) => {
        if (!e?.cacheKey || now - (e.ts || 0) > RECENT_OP_TTL_MS) return false;
        return e.cacheKey === cacheKey || e.cacheKey === altKey || e.altKey === cacheKey;
      }).flatMap((e) => e.messages || []);
    } catch {
      return [];
    }
  }, []);

  const saveOperatorMessageToSession = React.useCallback((userId, convId, message) => {
    if (!userId || !convId || !message) return;
    const isOp = message.role === "operator" || message.is_user === false;
    if (!isOp) return;
    try {
      const cacheKey = `${userId}_${convId}`;
      const raw = sessionStorage.getItem(SESSION_RECENT_OP_KEY);
      const arr = (raw ? JSON.parse(raw) : []).filter((e) => e?.ts && Date.now() - e.ts < RECENT_OP_TTL_MS);
      const entry = arr.find((e) => e.cacheKey === cacheKey);
      const msg = { ...message, role: "operator", is_user: false };
      if (entry) {
        const exists = (entry.messages || []).some(
          (m) => String(m.content || m.text || "").trim() === String(msg.content || msg.text || "").trim()
        );
        if (!exists) entry.messages = [...(entry.messages || []), msg];
      } else {
        arr.push({ cacheKey, ts: Date.now(), messages: [msg] });
      }
      sessionStorage.setItem(SESSION_RECENT_OP_KEY, JSON.stringify(arr.slice(-20)));
    } catch {}
  }, []);

  // Merge API messages with recently sent operator messages from cache + sessionStorage (prevents disappearing on refresh)
  const mergeWithRecentOperatorMessages = React.useCallback((apiMessages, cacheKey) => {
    const cache = messageCacheRef.current;
    let cached = cache?.get(cacheKey)?.messages || [];
    if (!cached.length && cacheKey) {
      const parts = cacheKey.split("_");
      if (parts.length >= 2) {
        const userId = parts[0];
        const rest = parts.slice(1).join("_");
        const altUserId = userId.startsWith("+") ? userId.slice(1) : `+${userId}`;
        const altKey = `${altUserId}_${rest}`;
        cached = cache?.get(altKey)?.messages || cached;
      }
    }
    if (!cached.length && cacheKey) {
      cached = getRecentOpFromSession(cacheKey);
    }
    const api = apiMessages || [];
    const now = Date.now();
    const RECENT_MS = 120000;
    const recentOperator = cached.filter((m) => {
      const isOp = m.is_user === false || m.role === "operator";
      const ts = m.timestamp ? new Date(m.timestamp).getTime() : 0;
      return isOp && now - ts < RECENT_MS;
    });
    const apiKeys = new Set(
      api.map((m) => `${String(m.content || m.text || "").trim()}|${(m.timestamp || "").slice(0, 19)}`)
    );
    const toAdd = recentOperator.filter((m) => {
      const key = `${String(m.content || m.text || "").trim()}|${(m.timestamp || "").slice(0, 19)}`;
      if (apiKeys.has(key)) return false;
      const mTs = m.timestamp ? new Date(m.timestamp).getTime() : 0;
      const inApi = api.some(
        (a) =>
          String(a.content || a.text || "").trim() === String(m.content || m.text || "").trim() &&
          Math.abs((a.timestamp ? new Date(a.timestamp).getTime() : 0) - mTs) < 60000
      );
      return !inApi;
    });
    if (toAdd.length === 0) return api;
    const combined = [...api, ...toAdd].sort(
      (a, b) => new Date(a?.timestamp || 0).getTime() - new Date(b?.timestamp || 0).getTime()
    );
    return combined;
  }, []);

  const buildPreviewHistory = React.useCallback((conversation) => {
    const preview = conversation?.last_message;
    if (!preview || typeof preview !== "object") return [];
    const text = String(preview.content ?? preview.text ?? "").trim();
    if (!text) return [];
    const timestamp =
      preview.timestamp ||
      conversation?.last_activity ||
      conversation?.last_message_at ||
      new Date().toISOString();
    return [
      {
        message_id: `preview_${conversation?.conversation_id || "chat"}_${timestamp}`,
        timestamp,
        is_user: Boolean(preview.is_user),
        content: text,
        text,
        type: "text",
        role: preview.is_user ? "user" : "assistant",
        handled_by: preview.is_user ? "human" : "ai",
      },
    ];
  }, []);

  const selectConversation = React.useCallback((conv) => {
    const cacheKey = `${conv.user_id}_${conv.conversation_id}`;
    const cached = messageCacheRef.current.get(cacheKey);
    const hasCachedMessages = cached?.messages?.length > 0;
    const previewHistory = hasCachedMessages ? [] : buildPreviewHistory(conv);
    setSelectedConversation({
      conversation: conv,
      history: hasCachedMessages ? cached.messages : previewHistory,
    });
    if (hasCachedMessages) {
      setHasMoreMessages(cached.hasMore ?? false);
      setMessagesLoading(false);
    } else if (previewHistory.length > 0) {
      setHasMoreMessages(false);
      setMessagesLoading(false);
    }
  }, [buildPreviewHistory]);

  const appendMessageToSelectedConversation = (newMessage) => {
    setSelectedConversation((previous) => {
      if (!previous) return previous;
      const updated = {
        ...previous,
        history: [...(previous.history || []), newMessage],
      };
      if (previous.conversation) {
        const cacheKey = `${previous.conversation.user_id}_${previous.conversation.conversation_id}`;
        messageCacheRef.current.set(cacheKey, {
          messages: updated.history,
          hasMore: hasMoreMessages,
          cachedAt: Date.now(),
        });
      }
      return updated;
    });
  };

  // Update chat list locally (move to top + update last_message) without calling /unified-chats
  const updateChatListLocally = (conversationId, userId, message) => {
    setActiveConversations((prev) => {
      const idx = prev.findIndex(
        (c) =>
          (conversationId && c.conversation_id === conversationId) ||
          (userId && c.user_id === userId)
      );
      if (idx < 0) return prev;
      const conv = prev[idx];
      const ts = message?.timestamp || new Date().toISOString();
      const updated = {
        ...conv,
        last_message: {
          content: message?.content ?? message?.text ?? "",
          is_user: message?.is_user ?? message?.role === "user",
          timestamp: ts,
        },
        last_activity: ts,
      };
      const rest = prev.filter((_, i) => i !== idx);
      return [updated, ...rest];
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

  // Fetch real data: on initial load (no search) rely on SSE only - no duplicate /unified-chats call
  useEffect(() => {
    const fetchLiveData = async () => {
      if (!isMountedRef.current) return;
      if (!activeConversations.length) {
        if (isMountedRef.current) setIsLoading(true);
      }

      // Initial load with no search: fetch both in parallel for faster load (SSE no longer sends initial list)
      if (!debouncedSearch.trim()) {
        Promise.all([
          getUnifiedChats("", 1, CHAT_LIST_PAGE_SIZE),
          getWaitingQueue(),
        ])
          .then(([chatsResponse, queueResponse]) => {
            if (!isMountedRef.current) return;
            if (chatsResponse?.success && chatsResponse.chats) {
              applyServerConversations(chatsResponse.chats);
              setHasMoreChats(chatsResponse.has_more ?? false);
              setChatPage(1);
              autoLoadedPagesRef.current = 1;
            }
            if (queueResponse?.success && queueResponse.queue) {
              applyWaitingQueue(queueResponse);
            }
          })
          .catch((err) => {
            if (!isMountedRef.current) return;
            console.warn("Live Chat initial fetch error:", err);
          })
          .finally(() => {
            if (isMountedRef.current) setIsLoading(false);
          });
        return;
      }

      try {
        let chatsResponse;
        try {
          chatsResponse = await getUnifiedChats(debouncedSearch, 1, CHAT_LIST_PAGE_SIZE);
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
              toast.error("Server is busy. Data will refresh when available.");
              return;
            }
          } else {
            throw err;
          }
        }
        if (chatsResponse?.success && isMountedRef.current) {
          const chats = chatsResponse.chats || chatsResponse.conversations || [];
          applyServerConversations(chats);
          setChatPage(1);
          setHasMoreChats(chatsResponse.has_more || false);
          setUseMockData(false);
          autoLoadedPagesRef.current = 1;

          const currentSelection = selectedConversationRef.current;
          if (currentSelection) {
            const updatedConv = chats.find(
              (c) => c.conversation_id === currentSelection.conversation.conversation_id
            );
            if (updatedConv && isMountedRef.current) {
              setSelectedConversation((prev) => ({ ...prev, conversation: updatedConv }));
            }
          }
        } else if (isMountedRef.current && !activeConversations.length) {
          loadMockData();
        }

        if (!debouncedSearch.trim()) {
          getWaitingQueue()
            .then((queueResponse) => {
              if (!isMountedRef.current) return;
              if (queueResponse?.success) {
                applyWaitingQueue(queueResponse);
              }
            })
            .catch(() => {});
        }
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
  }, [debouncedSearch, applyServerConversations]);

  useLiveChatSSE({
    enabled: !useMockData,
    isMountedRef,
    useMockDataRef,
    activeConversationsRef,
    selectedConversationRef,
    debouncedSearchRef,
    getUnifiedChats,
    chatListPageSize: CHAT_LIST_PAGE_SIZE,
    fetchConversationMessages,
    setActiveConversations: applyServerConversations,
    setNewConversationIds,
    setLastRefreshTime,
    setIsRefreshing,
    setSelectedConversation,
    updateChatListLocally,
    messageCacheRef,
    hasMoreMessagesRef,
    setIsLoading,
    setHasMoreChats,
    setChatPage,
    onOperatorMessageCached: saveOperatorMessageToSession,
  });

  // Fallback: if SSE doesn't populate, fetch once manually (single safety net)
  useEffect(() => {
    if (debouncedSearch.trim() || useMockData) return;
    const t = setTimeout(async () => {
      if (!isMountedRef.current) return;
      if (activeConversationsRef.current?.length > 0) return;
      setIsLoading(true);
      try {
        const r = await getUnifiedChats("", 1, CHAT_LIST_PAGE_SIZE);
        if (!isMountedRef.current) return;
        if (r?.success && r?.chats?.length > 0) {
          applyServerConversations(r.chats);
          setHasMoreChats(r.has_more ?? false);
          setChatPage(1);
          autoLoadedPagesRef.current = 1;
        }
      } catch (e) {
        console.warn("Live Chat fallback fetch failed:", e);
      } finally {
        if (isMountedRef.current) setIsLoading(false);
      }
    }, 15000);
    return () => clearTimeout(t);
  }, [debouncedSearch, useMockData, getUnifiedChats, applyServerConversations, setIsLoading, setHasMoreChats, setChatPage]);

  const selectedConversationId = selectedConversation?.conversation?.conversation_id;
  const selectedConversationUserId = selectedConversation?.conversation?.user_id;

  // ✅ Fetch messages when selected conversation changes (not polling)
  useEffect(() => {
    if (!selectedConversationId || !selectedConversationUserId || useMockData) {
      setMessagesLoading(false);
      return;
    }

    let cancelled = false;
    const loadingFallbackTimer = setTimeout(() => {
      if (!isMountedRef.current) return;
      if (cancelled) return;
      if (
        selectedConversationRef.current?.conversation?.conversation_id ===
        selectedConversationId
      ) {
        setMessagesLoading(false);
      }
    }, 12000);
    const cacheKey = `${selectedConversationUserId}_${selectedConversationId}`;
    const cached = messageCacheRef.current.get(cacheKey);
    const cacheAge = cached ? Date.now() - cached.cachedAt : Infinity;
    const cacheFresh = cached && cacheAge < MESSAGE_CACHE_TTL_MS;

    if (cached?.messages?.length) {
      setSelectedConversation((prev) => {
        if (!prev || prev.conversation?.conversation_id !== selectedConversationId) return prev;
        return { ...prev, history: cached.messages };
      });
      setHasMoreMessages(cached.hasMore);
    }

    if (cacheFresh) {
      setMessagesLoading(false);
      return () => {
        cancelled = true;
      };
    }

    const fetchMessages = async () => {
      setMessagesLoading(!cached?.messages?.length);
      try {
        const { messages, hasMore } = await fetchConversationMessages(
          selectedConversationUserId,
          selectedConversationId,
          0,
          null,
          0,
          100
        );
        if (!isMountedRef.current || cancelled) return;

        const merged = mergeWithRecentOperatorMessages(messages || [], cacheKey);

        messageCacheRef.current.set(cacheKey, {
          messages: merged,
          hasMore: hasMore || false,
          cachedAt: Date.now(),
        });

        setSelectedConversation((prev) => {
          if (!prev || prev.conversation?.conversation_id !== selectedConversationId) {
            return prev;
          }
          return { ...prev, history: merged };
        });
        setHasMoreMessages(hasMore);
      } catch (error) {
        if (isMountedRef.current && !cancelled) {
          const activeSelection = selectedConversationRef.current;
          const fallbackPreview = buildPreviewHistory(activeSelection?.conversation);
          const hasAnyFallback = (activeSelection?.history?.length || 0) > 0 || fallbackPreview.length > 0;
          setSelectedConversation((prev) => {
            if (!prev || prev.conversation?.conversation_id !== selectedConversationId) return prev;
            const existing = Array.isArray(prev.history) ? prev.history : [];
            if (existing.length > 0) return prev;
            return { ...prev, history: fallbackPreview };
          });
          setHasMoreMessages(false);
          const msg = error?.name === "AbortError" ? "Loading messages timed out - try again" : (error?.message || "Failed to load messages. Try again.");
          toast.error(hasAnyFallback ? `${msg} Showing latest available message.` : msg);
        }
      } finally {
        if (isMountedRef.current && !cancelled) {
          setMessagesLoading(false);
        }
      }
    };

    fetchMessages();

    return () => {
      cancelled = true;
      clearTimeout(loadingFallbackTimer);
    };
  }, [selectedConversationId, selectedConversationUserId, useMockData, fetchConversationMessages, mergeWithRecentOperatorMessages, buildPreviewHistory]);

  // Failsafe: if messages stay loading >26s (e.g. request hung), clear loading and notify
  const messagesLoadingStartRef = useRef(null);
  useEffect(() => {
    if (!messagesLoading) {
      messagesLoadingStartRef.current = null;
      return;
    }
    if (!messagesLoadingStartRef.current) messagesLoadingStartRef.current = Date.now();
    const t = setTimeout(() => {
      if (!isMountedRef.current) return;
      const elapsed = messagesLoadingStartRef.current ? Date.now() - messagesLoadingStartRef.current : 0;
      if (elapsed >= 26000) {
        setMessagesLoading(false);
        toast.error("Loading took too long. Try again or reload.");
      }
    }, 26000);
    return () => clearTimeout(t);
  }, [messagesLoading]);

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
  const loadMoreChats = React.useCallback(async () => {
    if (loadingMoreChats || !hasMoreChats) return;
    setLoadingMoreChats(true);
    try {
      const nextPage = chatPage + 1;
      const chatsResponse = await getUnifiedChats(debouncedSearch, nextPage, CHAT_LIST_PAGE_SIZE);
      if (chatsResponse.success && chatsResponse.chats) {
        setActiveConversations((prev) => {
          const existingKeys = new Set(
            prev.map((c) => `${c.user_id}_${c.conversation_id}`)
          );
          const deduped = chatsResponse.chats.filter(
            (c) => !existingKeys.has(`${c.user_id}_${c.conversation_id}`)
          );
          return [...prev, ...deduped];
        });
        setChatPage(nextPage);
        setHasMoreChats(chatsResponse.has_more || false);
      }
    } catch (error) {
      console.error("Error loading more chats:", error);
    } finally {
      setLoadingMoreChats(false);
    }
  }, [loadingMoreChats, hasMoreChats, chatPage, getUnifiedChats, debouncedSearch, CHAT_LIST_PAGE_SIZE]);

  const handleBotListScroll = React.useCallback(
    (event) => {
      const el = event.currentTarget;
      if (!el || loadingMoreChats || !hasMoreChats) return;
      const threshold = 140;
      const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (distanceToBottom <= threshold) {
        loadMoreChats();
      }
    },
    [loadingMoreChats, hasMoreChats, loadMoreChats]
  );

  // Auto-load extra pages to reduce missing conversations on first load
  useEffect(() => {
    if (debouncedSearch.trim()) {
      autoLoadedPagesRef.current = 1;
      return;
    }
    if (!hasMoreChats || loadingMoreChats) return;
    if (activeConversations.length >= 60) return;
    if (autoLoadedPagesRef.current >= 2) return;
    autoLoadedPagesRef.current += 1;
    loadMoreChats();
  }, [debouncedSearch, hasMoreChats, loadingMoreChats, activeConversations.length, loadMoreChats]);

  // ✅ Manual refresh handler
  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    try {
      const [chatsResponse, queueResponse] = await Promise.all([
        getUnifiedChats(debouncedSearch, 1, CHAT_LIST_PAGE_SIZE),
        getWaitingQueue(),
      ]);

      if (chatsResponse?.success && chatsResponse.chats) {
        let chats = chatsResponse.chats;
        const selected = selectedConversationRef.current?.conversation;
        if (selected) {
          const alreadyInList = chats.some(
            (c) => c.conversation_id === selected.conversation_id && c.user_id === selected.user_id
          );
          if (!alreadyInList) {
            chats = [selected, ...chats];
          }
        }

        const previousIds = new Set(
          (activeConversationsRef.current || []).map((c) => c.conversation_id)
        );
        const newIds = new Set(
          chats.filter((c) => !previousIds.has(c.conversation_id)).map((c) => c.conversation_id)
        );

  applyServerConversations(chats);
        setChatPage(1);
        setHasMoreChats(chatsResponse.has_more || false);
        setNewConversationIds(newIds);
        setLastRefreshTime(new Date());
  autoLoadedPagesRef.current = 1;
        toast.success("Conversations refreshed");

        // Auto-clear "new" badge after 10 seconds
        if (newIds.size > 0) {
          setTimeout(() => setNewConversationIds(new Set()), 10000);
        }
      }

      if (queueResponse?.success) {
        applyWaitingQueue(queueResponse);
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

  // ✅ Load more = 1 more day for this chat only (before=oldest, day_window=1)
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
        1,
        100
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
          if (selectedConversation?.conversation) {
            const key = `${selectedConversation.conversation.user_id}_${selectedConversation.conversation.conversation_id}`;
            messageCacheRef.current.set(key, {
              messages: deduped,
              hasMore,
              cachedAt: Date.now(),
            });
          }
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

  // ✅ Reload messages for currently selected conversation (last 1 day only)
  const reloadSelectedConversationMessages = async () => {
    if (!selectedConversation) return;

    const key = `${selectedConversation.conversation.user_id}_${selectedConversation.conversation.conversation_id}`;
    try {
      const { messages, hasMore } = await fetchConversationMessages(
        selectedConversation.conversation.user_id,
        selectedConversation.conversation.conversation_id,
        0,
        null,
        0,
        100
      );
      const merged = mergeWithRecentOperatorMessages(messages || [], key);
      setSelectedConversation((prev) => ({
        ...prev,
        history: merged,
      }));
      setHasMoreMessages(hasMore);
      messageCacheRef.current.set(key, {
        messages: merged,
        hasMore: hasMore || false,
        cachedAt: Date.now(),
      });
      toast.success(`Loaded ${merged.length} messages`);
    } catch (error) {
      console.error("Error reloading conversation messages:", error);
      toast.error("Failed to reload messages");
    }
  };

  // Auto-scroll: when chat opens go to last message (bottom); when near bottom and new messages, scroll.
  useEffect(() => {
    const conversationId = selectedConversation?.conversation?.conversation_id || null;
    const messageCount = selectedConversation?.history?.length || 0;
    const previousConversationId = previousConversationIdRef.current;
    const previousMessageCount = previousMessageCountRef.current;

    const hasConversationChanged =
      conversationId && conversationId !== previousConversationId;
    const hasNewMessages = messageCount > previousMessageCount;
    const isFirstLoadForConversation = messageCount > 0 && previousMessageCount === 0;

    const container = messagesContainerRef.current;
    const nearBottom = container
      ? container.scrollHeight - container.scrollTop - container.clientHeight < 120
      : true;

    const shouldScrollToBottomOnOpen =
      hasConversationChanged || isFirstLoadForConversation;
    const shouldScrollForNewMessages = hasNewMessages && nearBottom;

    previousConversationIdRef.current = conversationId;
    previousMessageCountRef.current = messageCount;

    if (shouldScrollToBottomOnOpen || shouldScrollForNewMessages) {
      const behavior = shouldScrollToBottomOnOpen ? "auto" : "smooth";
      messagesEndRef.current?.scrollIntoView({ behavior });
      // When opening a conversation, messages may render after this effect — scroll again after paint.
      if (shouldScrollToBottomOnOpen) {
        const rafId = requestAnimationFrame(() => {
          messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
        });
        return () => cancelAnimationFrame(rafId);
      }
    }
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
        setActiveConversations((prev) => {
          const exists = prev.some((conv) => conv.conversation_id === conversationId && conv.user_id === userId);
          const updated = prev.map((conv) =>
            conv.conversation_id === conversationId
              ? { ...conv, status: "human", operator_id: "operator_001" }
              : conv
          );
          if (exists) return updated;
          const fallback = selectedConversation?.conversation &&
            selectedConversation.conversation.conversation_id === conversationId
            ? selectedConversation.conversation
            : null;
          const newEntry = {
            ...(fallback || {
              conversation_id: conversationId,
              user_id: userId,
              user_name: userId,
              user_phone: "",
              status: "human",
              language: "ar",
              sentiment: "neutral",
              message_count: 0,
            }),
            status: "human",
            operator_id: "operator_001",
          };
          return [newEntry, ...updated];
        });
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

  const [isReleasing, setIsReleasing] = useState(false);
  const releasingRef = useRef(false);
  const handleReleaseToBot = async (conversationId, userId) => {
    if (releasingRef.current || isReleasing) return;
    releasingRef.current = true;
    setIsReleasing(true);
    try {
      const result = await releaseConversation(conversationId, userId);

      if (result?.success) {
        toast.success("Conversation released to bot!");
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
        const errMsg = result?.error ? `Failed to release: ${result.error}` : "Failed to release conversation";
        toast.error(errMsg);
      }
    } catch (error) {
      console.error("Error releasing conversation:", error);
      toast.error("Error releasing conversation");
    } finally {
      releasingRef.current = false;
      setIsReleasing(false);
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

  const sendingRef = React.useRef(false);
  const handleSendMessage = async () => {
    if (!messageInput.trim() || !selectedConversation || isSending || sendingRef.current) return;

    sendingRef.current = true;
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
        // Message will appear via SSE (no optimistic append to avoid duplicates)
        toast.success("Message sent to customer");
      } else {
        toast.error("Failed to send message");
      }
    } catch (error) {
      console.error("Error sending message:", error);
      toast.error("Error sending message");
    } finally {
      setIsSending(false);
      sendingRef.current = false;
    }
  };
  // Feedback handlers
  const handleFeedback = (message, feedbackType) => {
    if (feedbackType === "good") {
      // Submit positive feedback immediately
      submitFeedback({
        conversation_id: selectedConversation.conversation.conversation_id,
        message_id: message.message_id || message.id || `msg_${Date.now()}`,
        user_question: getPreviousUserMessage(message),
        bot_response: message.content,
        feedback_type: "good",
        language: selectedConversation.conversation.language,
      });
      toast.success("👍 Thanks for your feedback!");
    } else if (feedbackType === "wrong") {
      // Always show FAQ correction pop-up for bot messages (with or without FAQ match)
      setFaqCorrectionModal({ message });
    } else if (feedbackType === "like") {
      // Show modal to edit question + answer and save to FAQ (4 languages)
      setFeedbackModal({
        message,
        feedbackType: "like",
      });
    }
  };

  const getPreviousUserMessage = (botMessage) => {
    const messages = selectedConversation.history || [];
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

  const [editContent, setEditContent] = useState("");
  const [isSubmittingEdit, setIsSubmittingEdit] = useState(false);
  useEffect(() => {
    if (editMessageModal?.message) {
      setEditContent(editMessageModal.message.content || "");
    }
  }, [editMessageModal]);

  const [faqContext, setFaqContext] = useState(null);
  const [faqEditAnswer, setFaqEditAnswer] = useState("");
  const [faqContextLoading, setFaqContextLoading] = useState(false);
  const [faqSubmitting, setFaqSubmitting] = useState(false);
  useEffect(() => {
    if (!faqCorrectionModal?.message || !selectedConversation) {
      setFaqContext(null);
      return;
    }
    const msg = faqCorrectionModal.message;
    const faqMatch = msg.metadata?.faq_match || null;
    if (faqMatch) {
      setFaqContext({ faq_match: faqMatch, current_entry: msg.metadata?.current_entry ?? null });
      setFaqEditAnswer(msg.content || "");
      return;
    }
    setFaqContextLoading(true);
    setFaqEditAnswer(msg.content || "");
    const userId = selectedConversation.conversation.user_id;
    const conversationId = selectedConversation.conversation.conversation_id;
    const messageId = msg.message_id || msg.id;
    fetchFaqMatchContext({ userId, conversationId, messageId })
      .then((res) => {
        if (res.success && res.faq_match) {
          setFaqContext({ faq_match: res.faq_match, current_entry: res.current_entry ?? null });
          if (res.current_entry?.answer) setFaqEditAnswer(res.current_entry.answer);
          else setFaqEditAnswer(msg.content || "");
        } else {
          setFaqContext(null);
        }
      })
      .catch(() => setFaqContext(null))
      .finally(() => setFaqContextLoading(false));
  }, [faqCorrectionModal, selectedConversation]);

  const handleFaqSaveChange = async () => {
    if (!faqCorrectionModal?.message || !selectedConversation || !faqContext?.faq_match) return;
    const newAnswer = (faqEditAnswer || "").trim();
    if (!newAnswer) {
      toast.error("Text cannot be empty");
      return;
    }
    setFaqSubmitting(true);
    try {
      const res = await faqUpdateAnswer({
        faqId: faqContext.faq_match.faq_id,
        newAnswerText: newAnswer,
        updatedBy: "operator_001",
        source: "live_chat_dislike",
      });
      if (res.success) {
        const messageId = faqCorrectionModal.message.message_id || faqCorrectionModal.message.id;
        await editLiveChatMessage({
          userId: selectedConversation.conversation.user_id,
          conversationId: selectedConversation.conversation.conversation_id,
          messageId,
          newContent: newAnswer,
        });
        setSelectedConversation((prev) => {
          if (!prev?.history) return prev;
          return {
            ...prev,
            history: prev.history.map((m) =>
              (m.message_id || m.id) === messageId ? { ...m, content: newAnswer, text: newAnswer } : m
            ),
          };
        });
        setFaqCorrectionModal(null);
        toast.success("FAQ updated successfully");
      } else {
        toast.error(res.error || "Update failed");
      }
    } catch (e) {
      toast.error("Update failed");
    } finally {
      setFaqSubmitting(false);
    }
  };

  const handleFaqSaveNew = async () => {
    if (!faqCorrectionModal?.message || !selectedConversation) return;
    const newAnswer = (faqEditAnswer || "").trim();
    if (!newAnswer) {
      toast.error("Text cannot be empty");
      return;
    }
    const userQuestion = faqContext?.faq_match?.user_question ?? getPreviousUserMessage(faqCorrectionModal.message);
    const questionLanguage = faqContext?.faq_match?.user_language ?? selectedConversation.conversation.language ?? "ar";
    setFaqSubmitting(true);
    try {
      const res = await faqCreateFromLivechat({
        questionText: userQuestion,
        questionLanguage: questionLanguage === "franco" ? "franco" : questionLanguage,
        answerText: newAnswer,
        createdBy: "operator_001",
        source: "live_chat_dislike",
        relatedFaqId: faqContext?.faq_match?.faq_id,
        matchSimilarity: faqContext?.faq_match?.similarity,
      });
      if (res.success) {
        setFaqCorrectionModal(null);
        toast.success("New question added to FAQ");
      } else {
        toast.error(res.error || "Failed to add");
      }
    } catch (e) {
      toast.error("Failed to add");
    } finally {
      setFaqSubmitting(false);
    }
  };

  const submitEditMessage = async () => {
    if (!editMessageModal?.message || !selectedConversation) return;
    const newContent = (editContent || "").trim();
    if (!newContent) {
      toast.error("Text cannot be empty");
      return;
    }
    const msg = editMessageModal.message;
    const messageId = msg.message_id || msg.id;
    setIsSubmittingEdit(true);
    try {
      const result = await editLiveChatMessage({
        userId: selectedConversation.conversation.user_id,
        conversationId: selectedConversation.conversation.conversation_id,
        messageId,
        newContent,
      });
      if (result.success) {
        setSelectedConversation((prev) => {
          if (!prev || !prev.history) return prev;
          return {
            ...prev,
            history: prev.history.map((m) =>
              (m.message_id || m.id) === messageId
                ? { ...m, content: newContent, text: newContent }
                : m
            ),
          };
        });
        setEditMessageModal(null);
        toast.success("Reply updated");
      } else {
        toast.error(result.error || "Update failed");
      }
    } catch (err) {
      toast.error("Update failed");
    } finally {
      setIsSubmittingEdit(false);
    }
  };

  return (
    <div className="h-[calc(100vh-5rem)] -m-6 p-4 flex flex-col min-h-0">
      {/* Header - Operator Status + Refresh - compact */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-2 flex items-center justify-end flex-shrink-0"
      >
          {/* Manual Refresh Button */}
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
        {/* Conversations List - collapsible */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className={`${sidebarCollapsed ? "col-span-1" : "col-span-3"} whatsapp-sidebar flex flex-col overflow-hidden transition-all min-w-0`}
        >
          {sidebarCollapsed ? (
            <div className="flex flex-col items-center py-4 border-r border-slate-200">
              <button
                onClick={() => setSidebarCollapsed(false)}
                className="p-2 rounded-lg hover:bg-slate-100 text-slate-600"
                title="Expand conversations list"
              >
                <ChevronRightIcon className="w-5 h-5" />
              </button>
            </div>
          ) : (
            <>
          <div className="flex justify-end pr-2 pt-2">
            <button
              onClick={() => setSidebarCollapsed(true)}
              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500"
              title="Collapse sidebar"
            >
              <ChevronLeftIcon className="w-4 h-4" />
            </button>
          </div>
          {/* 1) With bot – first section - scroll contained, no overlap with chat */}
          <div
            className="whatsapp-sidebar-section flex-1 overflow-y-auto overflow-x-hidden min-h-0 relative z-0 bg-white"
            ref={botListRef}
            onScroll={handleBotListScroll}
          >
            <div className="sticky top-0 z-10 bg-white pb-3">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-bold text-slate-800 flex items-center">
                  <ChatBubbleLeftRightIcon className="w-5 h-5 mr-2 text-primary-600" />
                  With bot ({botConversations.length})
                </h3>
                <span className="text-xs text-slate-500 flex items-center space-x-1">
                  <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                  <span>Auto-updating</span>
                </span>
                {isLoading && (
                  <span className="text-xs text-slate-400">Loading...</span>
                )}
              </div>
              <div className="relative">
                <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  value={liveSearchQuery}
                  onChange={(e) => setLiveSearchQuery(e.target.value)}
                  placeholder="Search by name or phone..."
                  className="whatsapp-input w-full pl-9 pr-4"
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
            </div>
            <div className="space-y-2">
              {isLoading && botConversations.length === 0 ? (
                [...Array(5)].map((_, i) => (
                  <div key={i} className="p-3 rounded-lg bg-slate-50 border border-slate-100 animate-pulse">
                    <div className="h-4 w-3/4 bg-slate-200 rounded mb-2" />
                    <div className="h-3 w-1/2 bg-slate-100 rounded mb-2" />
                    <div className="h-3 w-full bg-slate-100 rounded" />
                  </div>
                ))
              ) : (
                <>
                  {liveBotConversations.length > 0 && (
                    <div className="pt-1">
                      <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">Live now</p>
                      <div className="space-y-2">
                        {liveBotConversations.map((conv) => (
                          <div
                            key={conv.conversation_id}
                            className={`p-3 rounded-lg cursor-pointer transition-all ${
                              selectedConversation?.conversation?.conversation_id ===
                              conv.conversation_id
                                ? "bg-primary-50 border-2 border-primary-300"
                                : "bg-slate-50 border border-slate-200 hover:bg-slate-100"
                            }`}
                            onClick={() => selectConversation(conv)}
                          >
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex-1">
                                <div className="flex items-center space-x-2">
                                  <p className="font-medium text-slate-800 text-sm">
                                    {conv.user_name}
                                  </p>
                                  <span className="inline-block px-2 py-0.5 bg-green-500 text-white text-xs font-bold rounded-full">
                                    Live
                                  </span>
                                  {newConversationIds.has(conv.conversation_id) && (
                                    <span className="inline-block px-2 py-0.5 bg-blue-500 text-white text-xs font-bold rounded-full animate-pulse">
                                      New
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-slate-500">
                                  {conv.user_phone || conv.phone_number || ""}
                                </p>
                              </div>
                              <SentimentIndicator sentiment={conv.sentiment} />
                            </div>
                            <div className="mb-2"><StatusBadge status={conv.status} /></div>
                            {(conv.last_message?.content ?? conv.last_message_text) && (
                              <p className="text-xs text-slate-600 truncate mb-1">
                                {conv.last_message?.content ?? conv.last_message_text ?? ""}
                              </p>
                            )}
                            <div className="flex items-center justify-between text-xs text-slate-500">
                              <span>{(conv.message_count ?? 0)} messages</span>
                              <span>{(conv.duration_seconds || 0) > 0 ? `${Math.floor(conv.duration_seconds / 60)}m` : ""}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {historyBotConversations.length > 0 && (
                    <div className="pt-3">
                      <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">Earlier</p>
                      <div className="space-y-2">
                        {historyBotConversations.map((conv) => (
                          <div
                            key={conv.conversation_id}
                            className={`p-3 rounded-lg cursor-pointer transition-all ${
                              selectedConversation?.conversation?.conversation_id ===
                              conv.conversation_id
                                ? "bg-primary-50 border-2 border-primary-300"
                                : "bg-slate-50 border border-slate-200 hover:bg-slate-100"
                            }`}
                            onClick={() => selectConversation(conv)}
                          >
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex-1">
                                <div className="flex items-center space-x-2">
                                  <p className="font-medium text-slate-800 text-sm">
                                    {conv.user_name}
                                  </p>
                                  {newConversationIds.has(conv.conversation_id) && (
                                    <span className="inline-block px-2 py-0.5 bg-blue-500 text-white text-xs font-bold rounded-full animate-pulse">
                                      New
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-slate-500">
                                  {conv.user_phone || conv.phone_number || ""}
                                </p>
                              </div>
                              <SentimentIndicator sentiment={conv.sentiment} />
                            </div>
                            <div className="mb-2"><StatusBadge status={conv.status} /></div>
                            {(conv.last_message?.content ?? conv.last_message_text) && (
                              <p className="text-xs text-slate-600 truncate mb-1">
                                {conv.last_message?.content ?? conv.last_message_text ?? ""}
                              </p>
                            )}
                            <div className="flex items-center justify-between text-xs text-slate-500">
                              <span>{(conv.message_count ?? 0)} messages</span>
                              <span>{(conv.duration_seconds || 0) > 0 ? `${Math.floor(conv.duration_seconds / 60)}m` : ""}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
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
            </>
          )}
        </motion.div>

        {/* Chat Window - much wider when sidebar collapsed */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className={`relative ${sidebarCollapsed ? "col-span-9" : "col-span-6"} whatsapp-chat-panel`}
        >
          {/* With bot floating panel - visible when sidebar collapsed (button in chat header) */}
          {sidebarCollapsed && botPanelOpen && (
                <>
                  <div
                    className="fixed inset-0 z-30 bg-black/20"
                    onClick={() => setBotPanelOpen(false)}
                    aria-hidden="true"
                  />
                  <motion.div
                    initial={{ x: -320 }}
                    animate={{ x: 0 }}
                    exit={{ x: -320 }}
                    className="fixed left-0 top-0 bottom-0 w-80 z-40 bg-white border-r border-slate-200 shadow-xl flex flex-col overflow-hidden"
                  >
                    <div className="p-4 border-b border-slate-200 flex items-center justify-between">
                      <h3 className="font-bold text-slate-800 flex items-center">
                        <ChatBubbleLeftRightIcon className="w-5 h-5 mr-2 text-primary-600" />
                        With bot ({botConversations.length})
                      </h3>
                      <button
                        onClick={() => setBotPanelOpen(false)}
                        className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
                      >
                        <XMarkIcon className="w-5 h-5" />
                      </button>
                    </div>
                    <div className="flex-1 overflow-y-auto p-3">
                      <div className="relative mb-3">
                        <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                        <input
                          type="text"
                          value={liveSearchQuery}
                          onChange={(e) => setLiveSearchQuery(e.target.value)}
                          placeholder="Search by name or phone..."
                          className="whatsapp-input w-full pl-9 pr-4"
                        />
                      </div>
                      <div className="space-y-2">
                        {liveBotConversations.length > 0 && (
                          <div className="pt-1">
                            <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">Live now</p>
                            <div className="space-y-2">
                              {liveBotConversations.map((conv) => (
                                <div
                                  key={conv.conversation_id}
                                  className={`p-3 rounded-lg cursor-pointer transition-all ${
                                    selectedConversation?.conversation?.conversation_id === conv.conversation_id
                                      ? "bg-primary-50 border-2 border-primary-300"
                                      : "bg-slate-50 border border-slate-200 hover:bg-slate-100"
                                  }`}
                                  onClick={() => {
                                    selectConversation(conv);
                                    setBotPanelOpen(false);
                                  }}
                                >
                                  <div className="flex items-start justify-between mb-1">
                                    <p className="font-medium text-slate-800 text-sm truncate">{conv.user_name}</p>
                                    <SentimentIndicator sentiment={conv.sentiment} />
                                  </div>
                                  <p className="text-xs text-slate-500 truncate">{conv.user_phone || conv.phone_number || ""}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {historyBotConversations.length > 0 && (
                          <div className="pt-3">
                            <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">Earlier</p>
                            <div className="space-y-2">
                              {historyBotConversations.map((conv) => (
                                <div
                                  key={conv.conversation_id}
                                  className={`p-3 rounded-lg cursor-pointer transition-all ${
                                    selectedConversation?.conversation?.conversation_id === conv.conversation_id
                                      ? "bg-primary-50 border-2 border-primary-300"
                                      : "bg-slate-50 border border-slate-200 hover:bg-slate-100"
                                  }`}
                                  onClick={() => {
                                    selectConversation(conv);
                                    setBotPanelOpen(false);
                                  }}
                                >
                                  <div className="flex items-start justify-between mb-1">
                                    <p className="font-medium text-slate-800 text-sm truncate">{conv.user_name}</p>
                                    <SentimentIndicator sentiment={conv.sentiment} />
                                  </div>
                                  <p className="text-xs text-slate-500 truncate">{conv.user_phone || conv.phone_number || ""}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {hasMoreChats && (
                          <button
                            onClick={loadMoreChats}
                            disabled={loadingMoreChats}
                            className="w-full py-2 mt-2 text-sm font-medium text-primary-600 hover:bg-primary-50 rounded-lg border border-primary-200"
                          >
                            {loadingMoreChats ? "Loading..." : "Load More"}
                          </button>
                        )}
                      </div>
                    </div>
                  </motion.div>
                </>
          )}
          {selectedConversation ? (
            <>
              {/* Chat Header - Fixed Height */}
              <div className="whatsapp-chat-header">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    {sidebarCollapsed && (
                      <button
                        onClick={() => setBotPanelOpen((o) => !o)}
                        className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm font-medium text-slate-700 mr-2"
                        title="With bot conversations"
                      >
                        <ChatBubbleLeftRightIcon className="w-4 h-4 text-primary-600" />
                        With bot ({botConversations.length})
                      </button>
                    )}
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
                          {selectedConversation.conversation.user_phone || selectedConversation.conversation.phone_number || ""}
                        </span>
                        <span className="flex items-center">
                          <GlobeAltIcon className="w-3 h-3 mr-1" />
                          {(selectedConversation.conversation.language || "ar").toUpperCase()}
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
                        className="whatsapp-pill"
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
                          disabled={isReleasing}
                          className="whatsapp-pill-outline"
                        >
                          <ArrowRightIcon className="w-4 h-4 mr-1" />
                          {isReleasing ? "Releasing..." : "Release to Bot"}
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
                            <p className="text-sm">{messageText}</p>
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
                        onKeyPress={(e) =>
                          e.key === "Enter" && !isSending && handleSendMessage()
                        }
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
                    With bot ({botConversations.length}) – Open list
                  </button>
                )}
              </div>
            </div>
          )}
        </motion.div>

        {/* Conversation Details - Right panel: Waiting + With operator above, User info below */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          className={`${sidebarCollapsed ? "col-span-2" : "col-span-3"} whatsapp-info-panel flex flex-col overflow-y-auto p-4`}
        >
          {/* Waiting for human + With operator - compact above user info */}
          <div className="space-y-2 mb-3 flex-shrink-0">
            <div className="whatsapp-info-card p-3">
              <h3 className="font-semibold text-slate-800 text-sm mb-1 flex items-center">
                <span className="mr-1.5">⏳</span>
                Waiting ({filteredWaitingQueue.length})
              </h3>
              {isLoading ? (
                <div className="animate-pulse h-12 bg-slate-100 rounded" />
              ) : (
                <>
                  <div className="space-y-1.5 max-h-20 overflow-y-auto">
                    {filteredWaitingQueue.length === 0 ? (
                      <p className="text-xs text-slate-400 italic py-1">None</p>
                    ) : (
                      filteredWaitingQueue.map((item) => {
                        const isUserRequested = userRequestedReasons.includes((item.reason || "").toLowerCase());
                        const readKey = `${item.user_id}_${item.conversation_id}`;
                        const readCount = readMessageCountByConv[readKey] ?? 0;
                        const unreadCount = Math.max(0, (item.message_count || 0) - readCount);
                        return (
                          <div
                            key={item.conversation_id}
                            className={`px-2 py-1.5 rounded cursor-pointer transition-colors text-xs ${
                              isUserRequested
                                ? "bg-orange-50 border border-orange-200 hover:bg-orange-100"
                                : "bg-amber-50 border border-amber-200 hover:bg-amber-100"
                            }`}
                            onClick={() => {
                              markWaitingConversationRead(item.user_id, item.conversation_id, item.message_count || 0);
                              const conv = activeConversations.find(
                                (c) =>
                                  c.conversation_id === item.conversation_id &&
                                  c.user_id === item.user_id
                              ) || {
                                conversation_id: item.conversation_id,
                                user_id: item.user_id,
                                user_name: item.user_name,
                                user_phone: item.user_phone,
                                status: "waiting_human",
                                language: item.language || "ar",
                                sentiment: item.sentiment,
                                message_count: item.message_count || 0,
                                last_message: item.last_message ? { content: item.last_message } : null,
                              };
                              selectConversation(conv);
                            }}
                          >
                            <div className="flex items-center justify-between gap-1">
                              <p className="font-medium text-slate-800 truncate">{item.user_name}</p>
                              {unreadCount > 0 && (
                                <span className="text-xs font-bold text-amber-600">{unreadCount}</span>
                              )}
                            </div>
                            <div className="flex items-center justify-between mt-0.5">
                              <span className="text-slate-500">{Math.floor(item.wait_time_seconds / 60)}m</span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleTakeOver(item.conversation_id, item.user_id);
                                }}
                                className="text-amber-600 hover:text-amber-700 font-medium"
                              >
                                Take Over
                              </button>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </>
              )}
            </div>
            <div className="whatsapp-info-card p-3">
              <h3 className="font-semibold text-slate-800 text-sm mb-1 flex items-center">
                <span className="mr-1.5">💬</span>
                With operator ({filteredWithOperator.length})
              </h3>
              {isLoading ? (
                <div className="animate-pulse h-10 bg-slate-100 rounded" />
              ) : (
                <>
                  <div className="space-y-1.5 max-h-16 overflow-y-auto">
                    {filteredWithOperator.length === 0 ? (
                      <p className="text-xs text-slate-400 italic py-1">None</p>
                    ) : (
                      filteredWithOperator.map((conv) => (
                        <div
                          key={conv.conversation_id}
                          className="px-2 py-1.5 rounded cursor-pointer bg-green-50 border border-green-200 hover:bg-green-100 transition-colors text-xs flex items-center justify-between"
                          onClick={() => selectConversation(conv)}
                        >
                          <span className="font-medium text-slate-800 truncate">{conv.user_name}</span>
                          <SentimentIndicator sentiment={conv.sentiment} />
                        </div>
                      ))
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
          {selectedConversation ? (
            <div className="space-y-4 flex-1 min-h-0">
              {/* User Info */}
              <div className="whatsapp-info-card">
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
              <div className="whatsapp-info-card">
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
              <div className="whatsapp-info-card">
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
            </div>
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

      {/* Edit bot message modal (dislike → edit reply, non-FAQ) */}
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

      {/* FAQ Correction modal (dislike on FAQ-sourced bot reply) */}
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
              View the original FAQ question that matched the user's message, the match score, and edit the answer. Save Change = update the same question in all languages. Save New = save the user's question with the answer as a new FAQ entry in all languages without changing the original.
            </p>
            {faqContextLoading ? (
              <p className="text-slate-500 text-sm">Loading match context...</p>
            ) : faqContext?.faq_match ? (
              <>
                <div className="space-y-3 mb-4 text-sm">
                  <div>
                    <span className="font-medium text-slate-600">Original FAQ question that matched the user's message:</span>
                    <p className="mt-1 p-2 bg-slate-50 rounded border border-slate-200 text-slate-800">
                      {faqContext.faq_match.stored_question || "—"}
                    </p>
                  </div>
                  <div>
                    <span className="font-medium text-slate-600">User's question:</span>
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
                    {faqSubmitting ? "..." : "Save New — Save user's question + answer as new FAQ in all languages (original unchanged)"}
                  </button>
                </div>
              </>
            ) : (
              <>
                {/* No FAQ match: show user question + editable answer + Save New only */}
                <div className="space-y-3 mb-4 text-sm">
                  <div>
                    <span className="font-medium text-slate-600">Original FAQ question:</span>
                    <p className="mt-1 p-2 bg-slate-100 rounded border border-slate-200 text-slate-500 italic">—</p>
                  </div>
                  <div>
                    <span className="font-medium text-slate-600">User's question:</span>
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
    </div>
  );
};

export default LiveChat;
