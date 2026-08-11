import { useState, useEffect, useRef, useCallback, useMemo } from "react";
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
  NewCustomerBadge,
} from "../components/LiveChat/ConversationIndicators";
import MobileLiveChatView from "../components/LiveChat/MobileLiveChatView";
import { useLiveChatSSE } from "../hooks/useLiveChatSSE";
import { useLiveChatMediaComposer } from "../hooks/useLiveChatMediaComposer";
import {
  endLiveChatConversation,
  editLiveChatMessage,
  fetchFaqMatchContext,
  faqUpdateAnswer,
  faqCreateFromLivechat,
  markConversationRead as markConversationReadApi,
} from "../utils/liveChatApi";
import { useAuth } from "../contexts/AuthContext";
import { errorMessage, getAxiosErrorCode, isAxiosLikeError } from "../utils/apiValidate";

/**
 * @param {unknown} userId
 * @param {unknown} channel
 * @returns {boolean}
 */
export const isSocialChannelUser = (userId, channel) => {
  const ch = String(channel || "").toLowerCase();
  if (ch === "instagram" || ch === "facebook") return true;
  const id = String(userId || "");
  return /^(?:[a-z0-9][a-z0-9_-]{0,63}:)?(?:instagram|facebook):/i.test(id);
};

const CHAT_LIST_PAGE_SIZE = 30;
const MESSAGE_CACHE_TTL_MS = 5 * 60 * 1000; // 5 min - avoid refetch when switching back to same conv

/**
 * @param {unknown} value
 * @returns {LiveChatConversation[]}
 */
const asConversationList = (value) =>
  Array.isArray(value) ? /** @type {LiveChatConversation[]} */ (value) : [];

/**
 * @param {unknown} value
 * @returns {QueueItem[]}
 */
const asQueueList = (value) => (Array.isArray(value) ? /** @type {QueueItem[]} */ (value) : []);

/**
 * @param {unknown} value
 * @returns {LiveChatMessage[]}
 */
const asMessageList = (value) => (Array.isArray(value) ? /** @type {LiveChatMessage[]} */ (value) : []);

/**
 * @param {unknown} value
 * @returns {string}
 */
const asText = (value) => (typeof value === "string" ? value : "");

/**
 * @param {unknown} value
 * @returns {number}
 */
const asTimestampMs = (value) => {
  if (!value) return 0;
  const parsed = new Date(/** @type {string | number | Date} */ (value)).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
};

/**
 * @param {LiveChatConversation | null | undefined} conv
 * @returns {conv is LiveChatConversation}
 */
const isConversation = (conv) => Boolean(conv);

/**
 * @param {LiveChatMessage} message
 * @returns {string}
 */
const messageBody = (message) => asText(message.content) || asText(message.text);

/**
 * Upstream 504 / client abort — both mean "server busy, retry later".
 * @param {unknown} error
 * @returns {boolean}
 */
const isGatewayTimeout = (error) => {
  if (getAxiosErrorCode(error) === "ECONNABORTED") return true;
  if (!isAxiosLikeError(error)) return false;
  return error.response?.status === 504;
};

/**
 * `last_message` arrives either as a preview object or as a raw string from the index.
 * @param {LiveChatMessage | string | null | undefined} value
 * @returns {string | undefined}
 */
const lastMessageContent = (value) => {
  if (value == null) return undefined;
  if (typeof value === "string") return value;
  return typeof value.content === "string" ? value.content : undefined;
};

/**
 * @param {{ mobile?: boolean }} props
 */
const LiveChat = ({ mobile = false }) => {
  const [searchParams] = useSearchParams();
  const { user: authUser } = useAuth();
  const operatorId = authUser?.id || authUser?.email || "unknown-operator";
  const [activeConversations, setActiveConversations] = useState(/** @type {LiveChatConversation[]} */ ([]));
  const [selectedConversation, setSelectedConversation] = useState(/** @type {SelectedConversation | null} */ (null));
  const [waitingQueue, setWaitingQueue] = useState(/** @type {QueueItem[]} */ ([]));
  const [messageInput, setMessageInput] = useState("");
  const { operatorStatus } = useOperatorStatus();
  const [isLoading, setIsLoading] = useState(true);
  const [useMockData, setUseMockData] = useState(false);
  const [feedbackModal, setFeedbackModal] = useState(/** @type {LiveChatMessageModalState | null} */ (null));
  const [editMessageModal, setEditMessageModal] = useState(/** @type {LiveChatMessageModalState | null} */ (null));
  const [faqCorrectionModal, setFaqCorrectionModal] = useState(/** @type {LiveChatMessageModalState | null} */ (null));

  // ✅ Auto-refresh state (Solution 1 + 4: Smart refresh with badges)
  const [lastRefreshTime, setLastRefreshTime] = useState(/** @type {Date | null} */ (new Date()));
  const [newConversationIds, setNewConversationIds] = useState(/** @type {Set<string>} */ (new Set())); // Track new conversations
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
  const [botDateFrom, setBotDateFrom] = useState("");
  const [botDateTo, setBotDateTo] = useState("");
  /** Smart Messaging send log → show only chats for customers who received this template in the date range */
  const [templateSendFilterId, setTemplateSendFilterId] = useState("");
  const [templateSendFilterActive, setTemplateSendFilterActive] = useState(false);
  const [templateSendFilterChats, setTemplateSendFilterChats] = useState(/** @type {LiveChatConversation[]} */ ([]));
  const [templateSendFilterMeta, setTemplateSendFilterMeta] = useState(/** @type {TemplateSendFilterMeta | null} */ (null));
  const [templateSendFilterLoading, setTemplateSendFilterLoading] = useState(false);
  const [messagingTemplates, setMessagingTemplates] = useState(
    /** @type {Record<string, SmartMessageTemplate | undefined>} */ ({})
  );
  const waitingSearchTerm = debouncedSearch.trim().toLowerCase();
  const normalizeUserIdentity = useCallback(
    /**
     * @param {unknown} value
     * @returns {string}
     */
    (value) => String(value || "").trim().replace(/^\+/, ""),
    []
  );
  /** Format phone for display: +9613000000 → +961 3 000 000 */
  const formatPhoneForDisplay = useCallback(
    /**
     * @param {string | undefined} phone
     * @returns {string}
     */
    (phone) => {
    const s = String(phone || "").trim();
    if (!s || s === "Unknown") return s;
    const digits = s.replace(/\D/g, "");
    if (digits.startsWith("961") && digits.length >= 10) {
      const national = digits.slice(3);
      return `+961 ${national.slice(0, 1)} ${national.slice(1, 4)} ${national.slice(4)}`;
    }
    if (s.startsWith("+")) return s;
    return s;
    },
    []
  );
  const [, setChatPage] = useState(1);
  const [nextCursor, setNextCursor] = useState(/** @type {string | null} */ (null));
  const [hasMoreChats, setHasMoreChats] = useState(false);
  const [loadingMoreChats, setLoadingMoreChats] = useState(false);
  const [rebuildingIndex, setRebuildingIndex] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [botPanelOpen, setBotPanelOpen] = useState(false); // With bot floating panel when sidebar collapsed
  const [mobileListSection, setMobileListSection] = useState("queue");
  const [mobileDetailsOpen, setMobileDetailsOpen] = useState(false);
  const [mobileFilterSheetOpen, setMobileFilterSheetOpen] = useState(false);
  const isMobileView = Boolean(mobile);

  // Split handover: 1) waiting (no operator yet) 2) with operator (handover done, chatting)
  const userRequestedReasons = useMemo(
    () => ["user_request", "customer_requested_human"],
    []
  );

  const normalizeConversationStatus = useCallback(
    /**
     * @param {string | undefined} status
     * @param {string | undefined} conversationState
     * @returns {string}
     */
    (status, conversationState) => {
    const raw = String(status || conversationState || "").toLowerCase();
    if (["human", "assigned_to_operator", "assigned"].includes(raw)) return "human";
    if (["waiting_human", "waiting_for_operator", "waiting", "pending"].includes(raw)) {
      return "waiting_human";
    }
    if (["closed", "resolved", "archived"].includes(raw)) return "closed";
    return "bot";
    },
    []
  );

  const normalizeIncomingConversation = useCallback(
    /**
     * @param {LiveChatConversation | null | undefined} conv
     * @returns {LiveChatConversation | null}
     */
    (conv) => {
    if (!conv || typeof conv !== "object") return null;
    const hta = conv.human_takeover_active;
    let postReleaseCooldownActive = false;
    const supUntil = conv.post_release_escalation_suppressed_until;
    if (supUntil) {
      const t = new Date(supUntil).getTime();
      if (!Number.isNaN(t) && t > Date.now()) {
        postReleaseCooldownActive = true;
      }
    }

    let normalizedStatus = normalizeConversationStatus(
      conv.status,
      conv.conversation_state
    );

    // Firestore/index can still have waiting_for_operator while human_takeover_active is false — trust release.
    if (hta === false || postReleaseCooldownActive) {
      if (normalizedStatus === "waiting_human") {
        normalizedStatus = "bot";
      }
      if (normalizedStatus === "human" && !conv.operator_id) {
        normalizedStatus = "bot";
      }
    }

    const lastActivity = conv.last_activity || conv.last_message_at || undefined;
    const rawLastMessage = conv.last_message;
    const previewText = conv.last_message_text ?? lastMessageContent(rawLastMessage) ?? "";
    /** @type {LiveChatMessage | null} */
    const normalizedLastMessage =
      rawLastMessage && typeof rawLastMessage === "object"
        ? rawLastMessage
        : previewText
          ? {
              content: previewText,
              timestamp: lastActivity,
              is_user: false,
            }
          : null;

    // Safety net: if backend status is temporarily stale but last bot message is a clear
    // handover/waiting phrase and no operator is assigned yet, surface it as waiting_human.
    // After "release to bot", last text can still be the waiting-queue line — do not re-classify as waiting.
    if (
      normalizedStatus === "bot" &&
      !conv.operator_id &&
      hta !== false &&
      !postReleaseCooldownActive
    ) {
      const lastText = String(
        (normalizedLastMessage && normalizedLastMessage.content) ||
          conv.last_message_text ||
          lastMessageContent(conv.last_message) ||
          ""
      ).toLowerCase();
      const waitingMarkers = [
        "تم تحويلك",
        "منكون معك",
        "you'll be transferred",
        "transferred to one of our staff",
        "we'll be with you shortly",
      ];
      if (waitingMarkers.some((marker) => lastText.includes(marker.toLowerCase()))) {
        normalizedStatus = "waiting_human";
      }
    }

    let outConversationState = conv.conversation_state;
    if ((hta === false || postReleaseCooldownActive) && normalizedStatus === "bot") {
      outConversationState = "bot_active";
    }

    return {
      ...conv,
      status: normalizedStatus,
      conversation_state: outConversationState,
      user_phone: conv.user_phone || conv.phone_number || "",
      last_activity: lastActivity,
      last_message: normalizedLastMessage,
    };
  }, [normalizeConversationStatus]);

  /**
   * @param {QueueItem[] | null | undefined} queue
   * @param {LiveChatConversation[] | null | undefined} activeList
   * @returns {QueueItem[]}
   */
  const mergeActiveWaitingIntoQueue = (queue, activeList) => {
    const activeWaiting = (activeList || []).filter((conv) => conv.status === "waiting_human");
    if (!activeWaiting.length) return queue ?? [];
    const queueKeys = new Set(
      (queue || []).map((item) => `${item.user_id}_${item.conversation_id}`)
    );
    /** @type {QueueItem[]} */
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
        last_message: lastMessageContent(conv.last_message) ?? "",
        reason: "user_request",
        sentiment: conv.sentiment || "neutral",
        language: conv.language || "ar",
        is_new_customer: conv.is_new_customer,
      });
    });
    return merged;
  };

  const mergeMissingActiveChats = useCallback(
    /**
     * @param {LiveChatConversation[]} incoming
     * @param {LiveChatConversation[] | null | undefined} existing
     * @returns {LiveChatConversation[]}
     */
    (incoming, existing) => {
    if (!Array.isArray(incoming)) return [];
    const existingList = existing || [];
    // Only preserve assigned-operator rows across pagination gaps. Stale waiting_human from a prior
    // render must not be re-injected when the conv drops off page 1 after release-to-bot (shows as "back on waiting").
    const keep = existingList.filter((conv) => conv.status === "human");
    if (!keep.length) return incoming;
    const incomingKeys = new Set(incoming.map((conv) => `${conv.user_id}_${conv.conversation_id}`));
    const missing = keep.filter((conv) => !incomingKeys.has(`${conv.user_id}_${conv.conversation_id}`));
    if (!missing.length) return incoming;
    return [...missing, ...incoming];
    },
    []
  );

  const applyServerConversations = useCallback(
    /**
     * @param {LiveChatConversation[] | unknown} incoming
     * @returns {void}
     */
    (incoming) => {
    if (!Array.isArray(incoming)) return;
    const normalizedIncoming = asConversationList(incoming)
      .map(normalizeIncomingConversation)
      .filter(isConversation);
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
    },
    [mergeMissingActiveChats, normalizeIncomingConversation]
  );

  const effectiveWaitingQueue = useMemo(
    () => mergeActiveWaitingIntoQueue(waitingQueue, activeConversations),
    [waitingQueue, activeConversations]
  );

  const filteredWaitingQueue = useMemo(() => {
    if (!waitingSearchTerm) return effectiveWaitingQueue;
    return effectiveWaitingQueue.filter((item) => {
      const name = (item.user_name || "").toLowerCase();
      const phone = (item.user_phone || "").toLowerCase();
      return name.includes(waitingSearchTerm) || phone.includes(waitingSearchTerm);
    });
  }, [effectiveWaitingQueue, waitingSearchTerm]);

  // Conversations where handover was done and we're talking with them (operator assigned)
  const withOperator = useMemo(
    () => {
      /**
       * @param {LiveChatConversation | null | undefined} conv
       * @returns {number}
       */
      const getLastTs = (conv) => {
        const lastMessage = conv?.last_message;
        const ts =
          conv?.last_activity ||
          (lastMessage && typeof lastMessage === "object" ? lastMessage.timestamp : undefined);
        return asTimestampMs(ts);
      };
      return activeConversations
        .filter((c) => {
          if (c.status !== "human") return false;
          // Some records can temporarily miss operator_id while still being assigned to a human.
          return true;
        })
        .sort((a, b) => getLastTs(b) - getLastTs(a));
    },
    [activeConversations]
  );

  const filteredWithOperator = useMemo(() => {
    if (!waitingSearchTerm) return withOperator;
    return withOperator.filter((conv) => {
      const name = (conv.user_name || "").toLowerCase();
      const phone = (conv.user_phone || "").toLowerCase();
      return name.includes(waitingSearchTerm) || phone.includes(waitingSearchTerm);
    });
  }, [withOperator, waitingSearchTerm]);
  // Only bot conversations (exclude waiting_human + with operator) - shown below, release to bot moves here
  const botConversations = useMemo(() => {
    const usersWithHumanOrWaiting = new Set(
      activeConversations
        .filter((c) => c.status === "human" || c.status === "waiting_human")
        .map((c) => normalizeUserIdentity(c.user_id))
        .filter(Boolean)
    );
    return activeConversations.filter((c) => {
      if (c.status !== "bot") return false;
      const normalizedUserId = normalizeUserIdentity(c.user_id);
      // Prevent "shadow" bot rows for users who already have an active human/waiting chat.
      return !usersWithHumanOrWaiting.has(normalizedUserId);
    });
  }, [activeConversations, normalizeUserIdentity]);

  const templateSendFilterViewActive =
    templateSendFilterActive && Boolean(templateSendFilterId);

  const botConversationsForList = useMemo(() => {
    if (!templateSendFilterViewActive) return botConversations;
    return (templateSendFilterChats || [])
      .map((c) => normalizeIncomingConversation(c))
      .filter(isConversation);
  }, [
    templateSendFilterViewActive,
    templateSendFilterChats,
    botConversations,
    normalizeIncomingConversation,
  ]);

  const templateSendFilterLabel = useMemo(() => {
    if (!templateSendFilterId) return "";
    const t = messagingTemplates[templateSendFilterId];
    return t?.name ? String(t.name) : templateSendFilterId;
  }, [templateSendFilterId, messagingTemplates]);

  const getConversationLastTs = useCallback(
    /**
     * @param {LiveChatConversation | null | undefined} conv
     * @returns {number}
     */
    (conv) => {
    const lastMessage = conv?.last_message;
    const ts =
      conv?.last_activity ||
      (lastMessage && typeof lastMessage === "object" ? lastMessage.timestamp : undefined);
    return asTimestampMs(ts);
    },
    []
  );

  const isBotDateFilterActive = Boolean(botDateFrom || botDateTo);

  const filteredBotConversations = useMemo(() => {
    if (templateSendFilterViewActive) {
      return botConversationsForList;
    }
    if (!isBotDateFilterActive) return botConversations;
    const start = botDateFrom ? new Date(`${botDateFrom}T00:00:00`) : null;
    const end = botDateTo ? new Date(`${botDateTo}T23:59:59.999`) : null;
    return botConversations.filter((conv) => {
      const lastTs = getConversationLastTs(conv);
      if (!lastTs) return false;
      if (start && lastTs < start.getTime()) return false;
      if (end && lastTs > end.getTime()) return false;
      return true;
    });
  }, [
    templateSendFilterViewActive,
    botConversationsForList,
    botConversations,
    botDateFrom,
    botDateTo,
    isBotDateFilterActive,
    getConversationLastTs,
  ]);

  const formatConversationListDate = useCallback(
    /**
     * @param {LiveChatConversation} conv
     * @returns {string}
     */
    (conv) => {
    const lastTs = getConversationLastTs(conv);
    if (!lastTs) return "No date";
    return new Date(lastTs).toLocaleDateString();
    },
    [getConversationLastTs]
  );

  const enrichWithRecency = useCallback(
    /**
     * @param {LiveChatConversation} conv
     * @returns {LiveChatListConversation}
     */
    (conv) => {
      const lastTs = getConversationLastTs(conv);
      const isRecent = lastTs > 0 && Date.now() - lastTs <= 15 * 60 * 1000;
      return { ...conv, _lastTs: lastTs, _isLive: Boolean(conv.is_live) || isRecent };
    },
    [getConversationLastTs]
  );

  const liveBotConversations = useMemo(
    () =>
      filteredBotConversations
        .map(enrichWithRecency)
        .filter((conv) => conv._isLive)
        .sort((a, b) => b._lastTs - a._lastTs),
    [filteredBotConversations, enrichWithRecency]
  );

  const historyBotConversations = useMemo(
    () =>
      filteredBotConversations
        .map(enrichWithRecency)
        .filter((conv) => !conv._isLive)
        .sort((a, b) => b._lastTs - a._lastTs),
    [filteredBotConversations, enrichWithRecency]
  );

  const mobileVisibleConversations = useMemo(() => {
    if (mobileListSection === "mine") return filteredWithOperator;
    if (mobileListSection === "bot") return [...liveBotConversations, ...historyBotConversations];
    return filteredWaitingQueue;
  }, [
    mobileListSection,
    filteredWithOperator,
    liveBotConversations,
    historyBotConversations,
    filteredWaitingQueue,
  ]);

  // Read count per waiting conversation for unread badge: key = `${user_id}_${conversation_id}`
  // Local state for optimistic UI; API unread_count is source of truth (persists across refresh)
  const [readMessageCountByConv, setReadMessageCountByConv] = useState(/** @type {Record<string, number>} */ ({}));
  const markConversationRead = useCallback(
    /**
     * @param {string} userId
     * @param {string} conversationId
     * @param {number} messageCount
     * @returns {void}
     */
    (userId, conversationId, messageCount) => {
    const key = `${userId}_${conversationId}`;
    setReadMessageCountByConv((prev) => ({ ...prev, [key]: messageCount }));
    // Persist to backend so unread stays 0 after refresh/update
    markConversationReadApi({ userId, conversationId }).catch((/** @type {unknown} */ err) =>
      console.warn("[LiveChat] mark-read API failed:", errorMessage(err))
    );
    },
    []
  );
  const markWaitingConversationRead = markConversationRead;

  /**
   * Merge selected conversation into waiting queue when refetching so it doesn't disappear from the list
   * @param {QueueItem[] | null | undefined} newQueue
   * @param {import('react').MutableRefObject<SelectedConversation | null>} selectedRef
   * @returns {QueueItem[]}
   */
  const mergeSelectedIntoWaitingQueue = (newQueue, selectedRef) => {
    const selected = selectedRef?.current;
    if (!selected?.conversation || selected.conversation.status !== "waiting_human") return newQueue ?? [];
    const c = selected.conversation;
    const inQueue = (newQueue ?? []).some((q) => q.conversation_id === c.conversation_id && q.user_id === c.user_id);
    if (inQueue) return newQueue ?? [];
    /** @type {QueueItem} */
    const synthetic = {
      conversation_id: c.conversation_id,
      user_id: c.user_id,
      user_name: c.user_name,
      user_phone: c.user_phone,
      wait_time_seconds: 0,
      message_count: c.message_count || 0,
      unread_count: c.unread_count,
      last_message: lastMessageContent(c.last_message) ?? "",
      reason: "user_request",
      sentiment: c.sentiment || "neutral",
    };
    return [synthetic, ...(newQueue ?? [])];
  };

  /**
   * @param {{ success?: boolean; queue?: QueueItem[] } | null | undefined} queueResponse
   * @returns {void}
   */
  const applyWaitingQueue = (queueResponse) => {
    const incoming = queueResponse?.queue;
    if (!Array.isArray(incoming)) return;
    // Always apply valid queue response - including empty. Previously we skipped empty
    // when we had cached items, which caused taken-over conversations to stay in
    // Waiting after refresh (API correctly returns empty/smaller queue, but we kept stale state).
    setWaitingQueue(mergeSelectedIntoWaitingQueue(incoming, selectedConversationRef));
  };

  const messagesContainerRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const messagesEndRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const selectedConversationRef = useRef(/** @type {SelectedConversation | null} */ (null));
  // ✅ Ref to track current conversations (fixes stale closure)
  const activeConversationsRef = useRef(/** @type {LiveChatConversation[]} */ ([]));
  const waitingQueueRef = useRef(/** @type {QueueItem[]} */ ([]));
  const cachedActiveConversationsRef = useRef(/** @type {LiveChatConversation[]} */ ([]));
  const cachedWaitingQueueRef = useRef(/** @type {QueueItem[]} */ ([]));
  const useMockDataRef = useRef(false); // ✅ Ref to track mock data status (fixes stale closure)
  const debouncedSearchRef = useRef("");
  const isMountedRef = useRef(true); // ✅ Prevent setState after unmount (fixes slow-down on repeated opens)
  const previousConversationIdRef = useRef(/** @type {string | null} */ (null));
  const previousMessageCountRef = useRef(0);
  const forceBottomOnOpenRef = useRef(/** @type {string | null} */ (null));
  const messageCacheRef = useRef(/** @type {Map<string, LiveChatMessageCacheEntry>} */ (new Map()));
  const hasMoreMessagesRef = useRef(true);
  const autoLoadedPagesRef = useRef(1);
  const botListRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const botLoadMoreSentinelRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const botListScrollThrottleRef = useRef(false);
  const botFloatingScrollRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const loadMoreInProgressRef = useRef(false);
  const loadMoreCooldownUntilRef = useRef(0);

  // Keep refs in sync with state
  useEffect(() => {
    selectedConversationRef.current = selectedConversation;
  }, [selectedConversation]);

  useEffect(() => {
    if (!isMobileView || selectedConversation?.conversation || !mobileDetailsOpen) return;
    setMobileDetailsOpen(false);
  }, [isMobileView, selectedConversation?.conversation, mobileDetailsOpen]);

  useEffect(() => {
    if (!isMobileView) return undefined;

    const handlePopState = () => {
      if (selectedConversationRef.current?.conversation) {
        setSelectedConversation(null);
        setMobileDetailsOpen(false);
      }
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [isMobileView]);

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
        const parsed = asConversationList(JSON.parse(cachedChats));
        if (parsed.length > 0) {
          const normalized = parsed.map(normalizeIncomingConversation).filter(isConversation);
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
        const parsed = asQueueList(JSON.parse(cachedQueue));
        if (parsed.length > 0) {
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
    getChatsByTemplateSendLog,
    getLiveConversations,
    getWaitingQueue,
    rebuildLiveChatIndex,
    simulateWebhook,
    getConversationMessages,
    takeoverConversation,
    releaseConversation,
    sendOperatorMessage,
    updateOperatorStatus,
    submitFeedback,
  } = useApi();

  // Smart Messaging HTTP API is product-disabled (403); do not fetch templates.
  const applyTemplateSendFilter = useCallback(async () => {
    if (!templateSendFilterId) {
      toast.error("Choose a template");
      return;
    }
    setTemplateSendFilterLoading(true);
    try {
      const r = await getChatsByTemplateSendLog(
        templateSendFilterId,
        botDateFrom,
        botDateTo
      );
      if (!r?.success) {
        toast.error(r?.error || "Filter failed");
        return;
      }
      setTemplateSendFilterChats(asConversationList(r.chats));
      setTemplateSendFilterMeta({
        log_entries_matched: r.log_entries_matched,
        distinct_recipients: r.distinct_recipients,
        matched_chats: r.matched_chats,
        index_scanned: r.index_scanned,
      });
      setTemplateSendFilterActive(true);
      setHasMoreChats(false);
      setNextCursor(null);
      const n = r.matched_chats ?? 0;
      toast.success(
        n > 0
          ? `${n} conversation(s) matched (send log + chat index)`
          : "No conversations matched in the index scan — try wider dates or Rebuild index"
      );
    } catch (e) {
      toast.error(errorMessage(e) || "Filter failed");
    } finally {
      setTemplateSendFilterLoading(false);
    }
  }, [
    templateSendFilterId,
    botDateFrom,
    botDateTo,
    getChatsByTemplateSendLog,
  ]);

  const clearTemplateSendFilter = useCallback(() => {
    setTemplateSendFilterActive(false);
    setTemplateSendFilterChats([]);
    setTemplateSendFilterMeta(null);
    setTemplateSendFilterId("");
  }, []);

  useEffect(() => {
    updateOperatorStatus(operatorId, operatorStatus).catch(() => {
      // Keep UI responsive even if status update endpoint is temporarily unavailable.
    });
  }, [operatorStatus, operatorId, updateOperatorStatus]);

  // Fetch conversation messages: use same axios as list (getUnifiedChats) so request hits same origin
  const fetchConversationMessages = useCallback(
    /**
     * @param {string} userId
     * @param {string} conversationId
     * @param {number} [days]
     * @param {string | null} [before]
     * @param {number} [day_window]
     * @param {number} [limit]
     * @returns {Promise<{ messages: LiveChatMessage[]; hasMore: boolean }>}
     */
    async (userId, conversationId, days = 0, before = null, day_window = 0, limit = 50) => {
      const result = await getConversationMessages(
        userId,
        conversationId,
        days,
        before,
        day_window,
        limit
      );
      return {
        messages: asMessageList(result?.messages),
        hasMore: Boolean(result?.hasMore),
      };
    },
    [getConversationMessages]
  );

  const SESSION_RECENT_OP_KEY = "live_chat_recent_op";
  const RECENT_OP_TTL_MS = 120000;

  const getRecentOpFromSession = useCallback(
    /**
     * @param {string} cacheKey
     * @returns {LiveChatMessage[]}
     */
    (cacheKey) => {
    try {
      const raw = sessionStorage.getItem(SESSION_RECENT_OP_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      /** @type {RecentOperatorSessionEntry[]} */
      const arr = Array.isArray(parsed) ? parsed : [];
      const now = Date.now();
      const parts = (cacheKey || "").split("_");
      const head = parts[0] ?? "";
      const altKey = parts.length >= 2
        ? `${head.startsWith("+") ? head.slice(1) : `+${head}`}_${parts.slice(1).join("_")}`
        : "";
      return arr.filter((e) => {
        if (!e?.cacheKey || now - (e.ts || 0) > RECENT_OP_TTL_MS) return false;
        return e.cacheKey === cacheKey || e.cacheKey === altKey || e.altKey === cacheKey;
      }).flatMap((e) => e.messages || []);
    } catch {
      return [];
    }
    },
    []
  );

  const saveOperatorMessageToSession = useCallback(
    /**
     * @param {string} userId
     * @param {string} convId
     * @param {LiveChatMessage} message
     * @returns {void}
     */
    (userId, convId, message) => {
    if (!userId || !convId || !message) return;
    const isOp = message.role === "operator" || message.is_user === false;
    if (!isOp) return;
    try {
      const cacheKey = `${userId}_${convId}`;
      const raw = sessionStorage.getItem(SESSION_RECENT_OP_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      /** @type {RecentOperatorSessionEntry[]} */
      const arr = (Array.isArray(parsed) ? parsed : []).filter(
        (/** @type {RecentOperatorSessionEntry} */ e) => e?.ts && Date.now() - e.ts < RECENT_OP_TTL_MS
      );
      const entry = arr.find((e) => e.cacheKey === cacheKey);
      /** @type {LiveChatMessage} */
      const msg = { ...message, role: "operator", is_user: false };
      if (entry) {
        const exists = (entry.messages || []).some(
          (m) => messageBody(m).trim() === messageBody(msg).trim()
        );
        if (!exists) entry.messages = [...(entry.messages || []), msg];
      } else {
        arr.push({ cacheKey, ts: Date.now(), messages: [msg] });
      }
      sessionStorage.setItem(SESSION_RECENT_OP_KEY, JSON.stringify(arr.slice(-20)));
    } catch {
      // sessionStorage may be unavailable
    }
    },
    []
  );

  // Merge API messages with recently sent operator messages from cache + sessionStorage (prevents disappearing on refresh)
  const mergeWithRecentOperatorMessages = useCallback(
    /**
     * @param {LiveChatMessage[]} apiMessages
     * @param {string} cacheKey
     * @returns {LiveChatMessage[]}
     */
    (apiMessages, cacheKey) => {
    const cache = messageCacheRef.current;
    let cached = cache?.get(cacheKey)?.messages || [];
    if (!cached.length && cacheKey) {
      const parts = cacheKey.split("_");
      if (parts.length >= 2) {
        const userId = parts[0] ?? "";
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
      const ts = asTimestampMs(m.timestamp);
      return isOp && now - ts < RECENT_MS;
    });
    const apiKeys = new Set(
      api.map((m) => `${messageBody(m).trim()}|${asText(m.timestamp).slice(0, 19)}`)
    );
    const toAdd = recentOperator.filter((m) => {
      const key = `${messageBody(m).trim()}|${asText(m.timestamp).slice(0, 19)}`;
      if (apiKeys.has(key)) return false;
      const mTs = asTimestampMs(m.timestamp);
      const inApi = api.some(
        (a) =>
          messageBody(a).trim() === messageBody(m).trim() &&
          Math.abs(asTimestampMs(a.timestamp) - mTs) < 60000
      );
      return !inApi;
    });
    if (toAdd.length === 0) return api;
    const combined = [...api, ...toAdd].sort(
      (a, b) => asTimestampMs(a?.timestamp) - asTimestampMs(b?.timestamp)
    );
    return combined;
    },
    [getRecentOpFromSession]
  );

  const buildPreviewHistory = useCallback(
    /**
     * @param {LiveChatConversation | null | undefined} conversation
     * @returns {LiveChatMessage[]}
     */
    (conversation) => {
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
    },
    []
  );

  const getConversationUnreadCount = useCallback(
    /**
     * @param {QueueItem | LiveChatConversation | null | undefined} conversation
     * @returns {number}
     */
    (conversation) => {
    if (!conversation) return 0;
    const readKey = `${conversation.user_id}_${conversation.conversation_id}`;
    const readCount = readMessageCountByConv[readKey] ?? 0;
    const msgCount = conversation.message_count || 0;
    if (readCount > 0 && readCount >= msgCount) return 0;
    if (typeof conversation.unread_count === "number") return conversation.unread_count;
    return Math.max(0, msgCount - readCount);
    },
    [readMessageCountByConv]
  );

  const buildConversationFromQueueItem = useCallback(
    /**
     * @param {QueueItem} item
     * @returns {LiveChatConversation}
     */
    (item) => {
    return activeConversations.find(
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
      last_message: item.last_message ? { content: lastMessageContent(item.last_message) } : null,
      is_new_customer: item.is_new_customer,
      wait_time_seconds: item.wait_time_seconds,
      reason: item.reason,
      unread_count: item.unread_count,
    };
    },
    [activeConversations]
  );

  const selectConversation = useCallback(
    /**
     * @param {LiveChatConversation} conv
     * @returns {void}
     */
    (conv) => {
    const cacheKey = `${conv.user_id}_${conv.conversation_id}`;
    const cached = messageCacheRef.current.get(cacheKey);
    const cachedMessages = cached?.messages ?? [];
    const hasCachedMessages = cachedMessages.length > 0;
    const knownCount = Math.max(conv?.message_count || 0, cachedMessages.length);
    markConversationRead(conv.user_id, conv.conversation_id, knownCount);
    setSelectedConversation({
      conversation: conv,
      history: hasCachedMessages ? cachedMessages : [],
    });
    if (hasCachedMessages) {
      setHasMoreMessages(cached?.hasMore ?? !cached?.isPartial);
      setMessagesLoading(false);
    } else {
      // No cached history: show loader, then render full fetched history in one pass.
      setHasMoreMessages(false);
      setMessagesLoading(true);
    }
    },
    [markConversationRead]
  );

  const openConversation = useCallback(
    /**
     * @param {LiveChatConversation} conv
     * @returns {void}
     */
    (conv) => {
    if (isMobileView && !selectedConversationRef.current?.conversation) {
      window.history.pushState({ mobileLiveChatOpen: true }, "");
    }
    setMobileDetailsOpen(false);
    selectConversation(conv);
    },
    [isMobileView, selectConversation]
  );

  const openWaitingConversation = useCallback(
    /**
     * @param {QueueItem} item
     * @returns {void}
     */
    (item) => {
    markWaitingConversationRead(item.user_id, item.conversation_id, item.message_count || 0);
    openConversation(buildConversationFromQueueItem(item));
    },
    [buildConversationFromQueueItem, markWaitingConversationRead, openConversation]
  );

  useEffect(() => {
    if (!selectedConversation?.conversation) return;
    const c = selectedConversation.conversation;
    const count = Math.max(c.message_count || 0, selectedConversation.history?.length || 0);
    markConversationRead(c.user_id, c.conversation_id, count);
  }, [
    selectedConversation?.conversation,
    selectedConversation?.conversation?.conversation_id,
    selectedConversation?.history?.length,
    markConversationRead,
  ]);

  /**
   * @param {LiveChatMessage} newMessage
   * @returns {void}
   */
  const appendMessageToSelectedConversation = (newMessage) => {
    setSelectedConversation((previous) => {
      if (!previous) return previous;
      /** @type {SelectedConversation} */
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
          isPartial: false,
        });
      }
      return updated;
    });
  };

  /**
   * Update chat list locally (move to top + update last_message) without calling /unified-chats
   * @param {string | undefined} conversationId
   * @param {string | undefined} userId
   * @param {LiveChatMessage} message
   * @returns {void}
   */
  const updateChatListLocally = (conversationId, userId, message) => {
    setActiveConversations((prev) => {
      let idx = -1;
      if (conversationId) {
        idx = prev.findIndex((c) => c.conversation_id === conversationId);
      } else if (userId) {
        // Fallback only when conversation ID is unavailable.
        idx = prev.findIndex((c) => c.user_id === userId);
      }
      const conv = idx >= 0 ? prev[idx] : undefined;
      if (!conv) return prev;
      const ts = message?.timestamp || new Date().toISOString();
      /** @type {LiveChatConversation} */
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

      // Initial load with no search: keep chats visible even if one endpoint fails.
      if (!debouncedSearch.trim()) {
        try {
          const [chatsResult, queueResult] = await Promise.allSettled([
            getUnifiedChats("", 1, CHAT_LIST_PAGE_SIZE),
            getWaitingQueue(),
          ]);
          if (!isMountedRef.current) return;

          let chatsResponse =
            chatsResult.status === "fulfilled" ? chatsResult.value : null;

          if (!chatsResponse?.success) {
            try {
              const fallback = await getLiveConversations("");
              if (fallback?.success && Array.isArray(fallback.conversations)) {
                chatsResponse = {
                  success: true,
                  chats: fallback.conversations,
                  has_more: false,
                };
              }
            } catch (fallbackErr) {
              console.warn("Live Chat initial fallback fetch error:", fallbackErr);
            }
          }

          if (chatsResponse?.success && Array.isArray(chatsResponse.chats)) {
            applyServerConversations(chatsResponse.chats);
            setHasMoreChats(chatsResponse.has_more ?? false);
            setNextCursor(chatsResponse.next_cursor ?? null);
            setChatPage(1);
            setUseMockData(false);
            autoLoadedPagesRef.current = 1;
          } else if (!activeConversationsRef.current?.length) {
            /* mock fallback removed — show empty/error honestly */ setUseMockData(false);
          }

          if (queueResult.status === "fulfilled" && queueResult.value?.success && queueResult.value?.queue) {
            applyWaitingQueue(queueResult.value);
          }
        } catch (err) {
          if (!isMountedRef.current) return;
          console.warn("Live Chat initial fetch error:", err);
        } finally {
          if (isMountedRef.current) setIsLoading(false);
        }
        return;
      }

      try {
        let chatsResponse;
        try {
          chatsResponse = await getUnifiedChats(debouncedSearch, 1, CHAT_LIST_PAGE_SIZE);
          if (!isMountedRef.current) return;
        } catch (err) {
          if (isGatewayTimeout(err)) {
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
            } catch {
              toast.error("Server is busy. Data will refresh when available.");
              return;
            }
          } else {
            throw err;
          }
        }
        if (chatsResponse?.success && isMountedRef.current) {
          const chats = asConversationList(chatsResponse.chats ?? chatsResponse.conversations);
          applyServerConversations(chats);
          setChatPage(1);
          setNextCursor(chatsResponse.next_cursor ?? null);
          setHasMoreChats(chatsResponse.has_more || false);
          setUseMockData(false);
          autoLoadedPagesRef.current = 1;

          const currentSelection = selectedConversationRef.current;
          if (currentSelection) {
            const updatedConv = chats.find(
              (c) => c.conversation_id === currentSelection.conversation.conversation_id
            );
            if (updatedConv && isMountedRef.current) {
              setSelectedConversation((prev) => (prev ? { ...prev, conversation: updatedConv } : prev));
            }
          }
        } else if (isMountedRef.current && !activeConversations.length) {
          /* mock fallback removed — show empty/error honestly */ setUseMockData(false);
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
        if (isGatewayTimeout(error)) {
          toast.error("Server is busy. Will retry automatically.");
        } else if (!activeConversations.length) {
          /* mock fallback removed — show empty/error honestly */ setUseMockData(false);
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
    getWaitingQueue,
    applyWaitingQueue,
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
      if (activeConversationsRef.current.length > 0) return;
      setIsLoading(true);
      try {
        let r = await getUnifiedChats("", 1, CHAT_LIST_PAGE_SIZE);
        if (!r?.success || asConversationList(r?.chats).length === 0) {
          const fallback = await getLiveConversations("");
          if (fallback?.success && Array.isArray(fallback.conversations) && fallback.conversations.length > 0) {
            r = { success: true, chats: fallback.conversations, has_more: false };
          }
        }
        if (!isMountedRef.current) return;
        if (r?.success && asConversationList(r?.chats).length > 0) {
          applyServerConversations(r.chats);
          setNextCursor(r.next_cursor ?? null);
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
  }, [debouncedSearch, useMockData, getUnifiedChats, getLiveConversations, applyServerConversations, setIsLoading, setHasMoreChats, setChatPage]);

  const selectedConversationId = selectedConversation?.conversation?.conversation_id;
  const selectedConversationUserId = selectedConversation?.conversation?.user_id;

  useEffect(() => {
    if (selectedConversationId) {
      // Force initial open at bottom even if messages hydrate in multiple steps.
      forceBottomOnOpenRef.current = selectedConversationId;
    } else {
      forceBottomOnOpenRef.current = null;
    }
  }, [selectedConversationId]);

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
    const cachedMessages = cached?.messages ?? [];
    const cacheAge = cached?.cachedAt ? Date.now() - cached.cachedAt : Infinity;
    const cacheFresh = cached && !cached.isPartial && cacheAge < MESSAGE_CACHE_TTL_MS;

    if (cachedMessages.length) {
      setSelectedConversation((prev) => {
        if (!prev || prev.conversation?.conversation_id !== selectedConversationId) return prev;
        return { ...prev, history: cachedMessages };
      });
      setHasMoreMessages(Boolean(cached?.hasMore));
    }

    if (cacheFresh) {
      setMessagesLoading(false);
      return () => {
        cancelled = true;
      };
    }

    const fetchMessages = async () => {
      setMessagesLoading(cachedMessages.length === 0);
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
          isPartial: false,
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
          const msg =
            error instanceof Error && error.name === "AbortError"
              ? "Loading messages timed out - try again"
              : errorMessage(error) || "Failed to load messages. Try again.";
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
  const messagesLoadingStartRef = useRef(/** @type {number | null} */ (null));
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

  const loadMoreChats = useCallback(async () => {
    if (templateSendFilterActive && templateSendFilterId) return;
    if (loadingMoreChats || !hasMoreChats || loadMoreInProgressRef.current) return;
    if (Date.now() < loadMoreCooldownUntilRef.current) return;
    if (!nextCursor) return; // Backend uses cursor-based pagination; need cursor for next page
    loadMoreInProgressRef.current = true;
    setLoadingMoreChats(true);
    try {
      /** @type {string | null} */
      let cursor = nextCursor;
      /** @type {boolean} */
      let hasMore = hasMoreChats;
      let pagesFetched = 0;
      let totalAdded = 0;
      const seenKeys = new Set(
        activeConversationsRef.current.map((c) => `${c.user_id}_${c.conversation_id}`)
      );

      // Fetch up to 3 pages in one go to skip duplicate-only pages.
      while (cursor && hasMore && pagesFetched < 3) {
        const chatsResponse = await getUnifiedChats(
          debouncedSearch,
          1,
          CHAT_LIST_PAGE_SIZE,
          cursor
        );
        pagesFetched += 1;
        if (!chatsResponse?.success) break;

        const normalized = asConversationList(chatsResponse.chats)
          .map(normalizeIncomingConversation)
          .filter(isConversation);
        const deduped = normalized.filter((c) => {
          const key = `${c.user_id}_${c.conversation_id}`;
          if (seenKeys.has(key)) return false;
          seenKeys.add(key);
          return true;
        });

        if (deduped.length > 0) {
          totalAdded += deduped.length;
          setActiveConversations((prev) => [...prev, ...deduped]);
        }

        cursor = chatsResponse.next_cursor || null;
        hasMore = Boolean(chatsResponse.has_more && cursor);

        // If we got new chats, stop here and let next user scroll load more.
        if (totalAdded > 0) break;
      }

      setNextCursor(cursor || null);
      setChatPage((p) => p + pagesFetched);
      setHasMoreChats(Boolean(hasMore));
      loadMoreCooldownUntilRef.current = Date.now() + 1500; // Cooldown 1.5s
    } catch (error) {
      console.error("Error loading more chats:", error);
      loadMoreCooldownUntilRef.current = Date.now() + 2000; // Cooldown on error too
    } finally {
      loadMoreInProgressRef.current = false;
      setLoadingMoreChats(false);
    }
  }, [
    loadingMoreChats,
    hasMoreChats,
    nextCursor,
    getUnifiedChats,
    debouncedSearch,
    normalizeIncomingConversation,
    templateSendFilterActive,
    templateSendFilterId,
  ]);

  const handleBotListScroll = useCallback(
    /**
     * @param {import('react').UIEvent<HTMLDivElement>} event
     * @returns {void}
     */
    (event) => {
      const el = event.currentTarget;
      if (templateSendFilterActive && templateSendFilterId) return;
      if (!el || loadingMoreChats || !hasMoreChats || loadMoreInProgressRef.current) return;
      if (botListScrollThrottleRef.current || Date.now() < loadMoreCooldownUntilRef.current) return;
      if (!nextCursor) return;
      const threshold = 280;
      const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (distanceToBottom <= threshold) {
        botListScrollThrottleRef.current = true;
        loadMoreChats();
        setTimeout(() => {
          botListScrollThrottleRef.current = false;
        }, 800);
      }
    },
    [
      loadingMoreChats,
      hasMoreChats,
      nextCursor,
      loadMoreChats,
      templateSendFilterActive,
      templateSendFilterId,
    ]
  );

  // Intersection Observer: load more when sentinel comes into view (avoid filteredBotConversations.length in deps to prevent loop)
  useEffect(() => {
    if (templateSendFilterActive && templateSendFilterId) return;
    const sentinel = botLoadMoreSentinelRef.current;
    const scrollRoot = botListRef.current;
    if (!sentinel || !scrollRoot || !hasMoreChats || loadingMoreChats) return;
    const obs = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;
        if (!entry?.isIntersecting || loadMoreInProgressRef.current) return;
        if (Date.now() < loadMoreCooldownUntilRef.current) return;
        loadMoreChats();
      },
      { root: scrollRoot, rootMargin: "200px", threshold: 0.1 }
    );
    obs.observe(sentinel);
    return () => obs.disconnect();
  }, [
    hasMoreChats,
    loadingMoreChats,
    loadMoreChats,
    templateSendFilterActive,
    templateSendFilterId,
  ]);

  // Auto-load extra pages to reduce missing conversations on first load
  useEffect(() => {
    if (debouncedSearch.trim()) {
      autoLoadedPagesRef.current = 1;
      return;
    }
    if (!hasMoreChats || loadingMoreChats || !nextCursor) return;
    if (activeConversations.length >= 60) return;
    if (autoLoadedPagesRef.current >= 2) return;
    if (Date.now() < loadMoreCooldownUntilRef.current) return;
    autoLoadedPagesRef.current += 1;
    loadMoreChats();
  }, [debouncedSearch, hasMoreChats, loadingMoreChats, nextCursor, activeConversations.length, loadMoreChats]);

  // ✅ Manual refresh handler
  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    try {
      const [chatsResult, queueResult] = await Promise.allSettled([
        getUnifiedChats(debouncedSearch, 1, CHAT_LIST_PAGE_SIZE),
        getWaitingQueue(),
      ]);

      let chatsResponse =
        chatsResult.status === "fulfilled" ? chatsResult.value : null;

      if (!chatsResponse?.success) {
        try {
          const fallback = await getLiveConversations(debouncedSearch);
          if (fallback?.success && Array.isArray(fallback.conversations)) {
            chatsResponse = {
              success: true,
              chats: fallback.conversations,
              has_more: false,
            };
          }
        } catch (fallbackErr) {
          console.warn("Live Chat manual refresh fallback error:", fallbackErr);
        }
      }

      if (chatsResponse?.success && chatsResponse.chats) {
        let chats = asConversationList(chatsResponse.chats);
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
          activeConversationsRef.current.map((c) => c.conversation_id)
        );
        const newIds = new Set(
          chats.filter((c) => !previousIds.has(c.conversation_id)).map((c) => c.conversation_id)
        );

        applyServerConversations(chats);
        setChatPage(1);
        setNextCursor(chatsResponse.next_cursor ?? null);
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

      if (queueResult.status === "fulfilled" && queueResult.value?.success) {
        applyWaitingQueue(queueResult.value);
      }
      if (!chatsResponse?.success) {
        toast.error("Failed to refresh conversations");
      }

      if (chatsResult.status === "rejected") {
        console.warn("Live Chat manual refresh error:", chatsResult.reason);
      }
      if (queueResult.status === "rejected") {
        console.warn("Live Chat queue refresh error:", queueResult.reason);
      }
    } catch (error) {
      console.error("Error refreshing conversations:", error);
      if (getAxiosErrorCode(error) === "ECONNABORTED") {
        toast.error("Request timeout - server may be busy. Try again.");
      } else {
        toast.error("Failed to refresh conversations");
      }
    } finally {
      setIsRefreshing(false);
    }
  };

  /**
   * ✅ Format last refresh time as relative time (e.g., "2 seconds ago")
   * @returns {string}
   */
  const formatLastRefreshTime = () => {
    const diff = Math.floor((Date.now() - (lastRefreshTime?.getTime() ?? Date.now())) / 1000); // seconds

    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  };

  // ✅ Load more = next 30 messages (day_window=0 = no day limit, fast load)
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
        0,
        30
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
              isPartial: false,
            });
          }
          return prev ? { ...prev, history: deduped } : prev;
        });
      }
      setHasMoreMessages(hasMore);
    } catch (e) {
      console.error("Load more messages error:", e);
    } finally {
      setLoadingMoreMessages(false);
    }
  };

  // ✅ Reload messages for currently selected conversation (all history, no day limit)
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
        30
      );
      const merged = mergeWithRecentOperatorMessages(messages || [], key);
      setSelectedConversation((prev) => (prev ? { ...prev, history: merged } : prev));
      setHasMoreMessages(hasMore);
      messageCacheRef.current.set(key, {
        messages: merged,
        hasMore: hasMore || false,
        cachedAt: Date.now(),
        isPartial: false,
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
    const shouldForceBottom =
      conversationId && forceBottomOnOpenRef.current === conversationId;
    const nearBottom = container
      ? container.scrollHeight - container.scrollTop - container.clientHeight < 120
      : true;

    const shouldScrollToBottomOnOpen =
      hasConversationChanged || isFirstLoadForConversation || shouldForceBottom;
    const shouldScrollForNewMessages =
      hasNewMessages && (nearBottom || shouldForceBottom);

    previousConversationIdRef.current = conversationId;
    previousMessageCountRef.current = messageCount;

    if (shouldScrollToBottomOnOpen || shouldScrollForNewMessages) {
      const behavior = shouldScrollToBottomOnOpen ? "auto" : "smooth";
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
      messagesEndRef.current?.scrollIntoView({ behavior });
      // When opening a conversation, messages may render after this effect — scroll again after paint.
      if (shouldScrollToBottomOnOpen || shouldForceBottom) {
        const rafId = requestAnimationFrame(() => {
          if (container) {
            container.scrollTop = container.scrollHeight;
          }
          messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
        });
        const settleId = setTimeout(() => {
          if (
            forceBottomOnOpenRef.current === conversationId &&
            messageCount > 0
          ) {
            forceBottomOnOpenRef.current = null;
          }
        }, 400);
        return () => {
          cancelAnimationFrame(rafId);
          clearTimeout(settleId);
        };
      }
    }
  }, [selectedConversation?.conversation?.conversation_id, selectedConversation?.history?.length]);

  /**
   * @param {string} conversationId
   * @param {string} userId
   * @returns {Promise<void>}
   */
  const handleTakeOver = async (conversationId, userId) => {
    console.log("🔄 handleTakeOver called with:", { conversationId, userId });

    if (!conversationId || !userId) {
      console.error("❌ Missing conversationId or userId:", { conversationId, userId });
      toast.error("Cannot take over: missing conversation or user ID");
      return;
    }
    if (isSocialChannelUser(userId, selectedConversation?.conversation?.channel)) {
      toast.error("Instagram/Facebook conversations are read-only. Use WhatsApp handoff links.");
      return;
    }

    try {
      const result = await takeoverConversation(
        conversationId,
        userId,
        operatorId
      )

      console.log("📋 Takeover result:", result);

      if (result.success) {
        toast.success("Conversation taken over successfully");
        // Update conversation status locally
        setActiveConversations((prev) => {
          const exists = prev.some((conv) => conv.conversation_id === conversationId && conv.user_id === userId);
          const updated = prev.map((conv) =>
            conv.conversation_id === conversationId && conv.user_id === userId
              ? { ...conv, status: "human", operator_id: operatorId }
              : conv
          );
          if (exists) return updated;
          const fallback = selectedConversation?.conversation &&
            selectedConversation.conversation.conversation_id === conversationId
            ? selectedConversation.conversation
            : null;
          /** @type {LiveChatConversation} */
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
            operator_id: operatorId,
          };
          return [newEntry, ...updated];
        });
        // Update selected conversation if it's the one we took over
        if (
          selectedConversation?.conversation?.conversation_id === conversationId
        ) {
          setSelectedConversation((prev) =>
            prev
              ? {
                  ...prev,
                  conversation: {
                    ...prev.conversation,
                    status: "human",
                    operator_id: operatorId,
                  },
                }
              : prev
          );
        }
        // Remove from waiting queue (match by both user_id and conversation_id)
        setWaitingQueue((prev) =>
          prev.filter(
            (item) =>
              !(item.conversation_id === conversationId && item.user_id === userId)
          )
        );
      } else {
        console.error("❌ Takeover failed:", result.error);
        toast.error(`Failed to take over: ${result.error || "Unknown error"}`);
      }
    } catch (error) {
      console.error("❌ Error taking over conversation:", error);
      toast.error(`Error: ${errorMessage(error) || "Unknown error"}`);
    }
  };

  const [isReleasing, setIsReleasing] = useState(false);
  const releasingRef = useRef(false);
  /**
   * @param {string} conversationId
   * @param {string} userId
   * @returns {Promise<void>}
   */
  const handleReleaseToBot = async (conversationId, userId) => {
    if (releasingRef.current || isReleasing) return;
    releasingRef.current = true;
    setIsReleasing(true);
    try {
      const result = await releaseConversation(conversationId, userId);

      if (result?.success) {
        toast.success("Conversation released to bot!");
        const postRelUntil = new Date(Date.now() + 45 * 60 * 1000).toISOString();
        // Update conversation status locally
        setActiveConversations((prev) =>
          prev.map((conv) =>
            conv.conversation_id === conversationId && conv.user_id === userId
              ? {
                  ...conv,
                  status: "bot",
                  operator_id: null,
                  human_takeover_active: false,
                  post_release_escalation_suppressed_until: postRelUntil,
                  conversation_state: "bot_active",
                }
              : conv
          )
        );
        setWaitingQueue((prev) =>
          prev.filter(
            (item) =>
              !(item.conversation_id === conversationId && item.user_id === userId)
          )
        );
        // Update selected conversation if it's the one we released
        if (
          selectedConversation?.conversation?.conversation_id === conversationId
        ) {
          setSelectedConversation((prev) =>
            prev
              ? {
                  ...prev,
                  conversation: {
                    ...prev.conversation,
                    status: "bot",
                    operator_id: null,
                    human_takeover_active: false,
                    post_release_escalation_suppressed_until: postRelUntil,
                    conversation_state: "bot_active",
                  },
                }
              : prev
          );
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

  /**
   * @param {string} conversationId
   * @param {string} userId
   * @returns {Promise<void>}
   */
  const handleEndConversation = async (conversationId, userId) => {
    try {
      const result = await endLiveChatConversation({
        conversationId,
        userId,
        operatorId: operatorId,
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

  const sendingRef = useRef(false);
  const handleSendMessage = async () => {
    if (!messageInput.trim() || !selectedConversation || isSending || sendingRef.current) return;
    if (isSocialChannelUser(selectedConversation.conversation?.user_id, selectedConversation.conversation?.channel)) {
      toast.error("Instagram/Facebook conversations are read-only. Use WhatsApp handoff links.");
      return;
    }

    sendingRef.current = true;
    setIsSending(true);
    const messageToSend = messageInput.trim();
    setMessageInput(""); // Clear immediately to prevent duplicate sends

    // Optimistic append BEFORE API call so it's in state when SSE arrives (prevents double display).
    // If we append after API: SSE can arrive first → add message → API returns → append again = duplicate.
    const optimisticMessage = {
      message_id: `local_op_${Date.now()}`,
      timestamp: new Date().toISOString(),
      is_user: false,
      role: "operator",
      handled_by: "human",
      type: "text",
      content: messageToSend,
      text: messageToSend,
    };
    appendMessageToSelectedConversation(optimisticMessage);
    saveOperatorMessageToSession(
      selectedConversation.conversation.user_id,
      selectedConversation.conversation.conversation_id,
      optimisticMessage
    );
    updateChatListLocally(
      selectedConversation.conversation.conversation_id,
      selectedConversation.conversation.user_id,
      optimisticMessage
    );

    const idempotencyKey =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `op_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;

    try {
      const result = await sendOperatorMessage(
        selectedConversation.conversation.conversation_id,
        selectedConversation.conversation.user_id,
        messageToSend,
        operatorId,
        "text",
        idempotencyKey
      );

      if (result.success) {
        toast.success("Message sent to customer");
      } else {
        toast.error("Failed to send message");
        // Rollback optimistic message on failure
        setSelectedConversation((prev) => {
          if (!prev?.history) return prev;
          const filtered = prev.history.filter((m) => m.message_id !== optimisticMessage.message_id);
          if (messageCacheRef?.current && prev.conversation) {
            const cacheKey = `${prev.conversation.user_id}_${prev.conversation.conversation_id}`;
            const existing = messageCacheRef.current.get(cacheKey);
            messageCacheRef.current.set(cacheKey, {
              messages: filtered,
              hasMore: existing?.hasMore ?? false,
              cachedAt: Date.now(),
              isPartial: existing?.isPartial ?? false,
            });
          }
          return { ...prev, history: filtered };
        });
      }
    } catch (error) {
      console.error("Error sending message:", error);
      toast.error("Error sending message");
      // Rollback optimistic message on error
      setSelectedConversation((prev) => {
        if (!prev?.history) return prev;
        const filtered = prev.history.filter((m) => m.message_id !== optimisticMessage.message_id);
        if (messageCacheRef?.current && prev.conversation) {
          const cacheKey = `${prev.conversation.user_id}_${prev.conversation.conversation_id}`;
          const existing = messageCacheRef.current.get(cacheKey);
          messageCacheRef.current.set(cacheKey, {
            messages: filtered,
            hasMore: existing?.hasMore ?? false,
            cachedAt: Date.now(),
            isPartial: existing?.isPartial ?? false,
          });
        }
        return { ...prev, history: filtered };
      });
    } finally {
      setIsSending(false);
      sendingRef.current = false;
    }
  };
  /**
   * Feedback handlers
   * @param {LiveChatMessage} message
   * @param {string} feedbackType
   * @returns {void}
   */
  const handleFeedback = (message, feedbackType) => {
    if (!selectedConversation) return;
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

  /**
   * @param {LiveChatMessage} botMessage
   * @returns {string}
   */
  const getPreviousUserMessage = (botMessage) => {
    const messages = selectedConversation?.history || [];
    const botIndex = messages.findIndex((m) => m === botMessage);

    // Find the previous user message
    for (let i = botIndex - 1; i >= 0; i--) {
      const candidate = messages[i];
      if (candidate?.is_user) {
        return asText(candidate.content);
      }
    }

    return "Unknown question";
  };

  /**
   * @param {string} correctAnswer
   * @param {string} feedbackReason
   * @returns {Promise<void>}
   */
  const submitCorrection = async (correctAnswer, feedbackReason) => {
    if (!selectedConversation || !feedbackModal) return;
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

  /**
   * @param {string} editedQuestion
   * @param {string} editedAnswer
   * @returns {Promise<void>}
   */
  const submitLikeToFaq = async (editedQuestion, editedAnswer) => {
    if (!selectedConversation || !feedbackModal) return;
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

  const [faqContext, setFaqContext] = useState(/** @type {LiveChatFaqContext | null} */ (null));
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
    const messageId = msg.message_id || msg.id || "";
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
        faqId: faqContext.faq_match.faq_id ?? "",
        newAnswerText: newAnswer,
        updatedBy: operatorId,
        source: "live_chat_dislike",
      });
      if (res.success) {
        const messageId = faqCorrectionModal.message.message_id || faqCorrectionModal.message.id || "";
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
    } catch {
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
        createdBy: operatorId,
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
    } catch {
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
    const messageId = msg.message_id || msg.id || "";
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
    } catch {
      toast.error("Update failed");
    } finally {
      setIsSubmittingEdit(false);
    }
  };

  const sharedOverlayModals = (
    <>
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
          conversation={selectedConversation?.conversation}
          onClose={() => setFeedbackModal(null)}
          onSubmit={submitCorrection}
        />
      )}

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
              View the original FAQ question that matched the user{"'"}s message, the match score, and edit the answer. Save Change = update the same question in all languages. Save New = save the user{"'"}s question with the answer as a new FAQ entry in all languages without changing the original.
            </p>
            {faqContextLoading ? (
              <p className="text-slate-500 text-sm">Loading match context...</p>
            ) : faqContext?.faq_match ? (
              <>
                <div className="space-y-3 mb-4 text-sm">
                  <div>
                    <span className="font-medium text-slate-600">Original FAQ question that matched the user{"'"}s message:</span>
                    <p className="mt-1 p-2 bg-slate-50 rounded border border-slate-200 text-slate-800">
                      {faqContext.faq_match.stored_question || "—"}
                    </p>
                  </div>
                  <div>
                    <span className="font-medium text-slate-600">User{"'"}s question:</span>
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
                    {faqSubmitting
                      ? "..."
                      : "Save New — Save user\u2019s question + answer as new FAQ in all languages (original unchanged)"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="space-y-3 mb-4 text-sm">
                  <div>
                    <span className="font-medium text-slate-600">Original FAQ question:</span>
                    <p className="mt-1 p-2 bg-slate-100 rounded border border-slate-200 text-slate-500 italic">—</p>
                  </div>
                  <div>
                    <span className="font-medium text-slate-600">User{"'"}s question:</span>
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
    </>
  );

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
        {sharedOverlayModals}
      </>
    );
  }

  return (
    <>
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
          {/* 1) With bot – header fixed above, list scrolls below */}
          <div className="whatsapp-sidebar-section flex-1 flex flex-col min-h-0 bg-white overflow-hidden">
            {/* Header - fixed at top, never scrolls */}
            <div className="flex-shrink-0 pt-2 pb-3 bg-white border-b border-slate-100">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-bold text-slate-800 flex items-center">
                  <ChatBubbleLeftRightIcon className="w-5 h-5 mr-2 text-primary-600" />
                  {templateSendFilterViewActive ? (
                    <>
                      Template: {templateSendFilterLabel} ({filteredBotConversations.length})
                    </>
                  ) : (
                    <>With bot ({filteredBotConversations.length})</>
                  )}
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
              <div className="mt-2 grid grid-cols-2 gap-2">
                <input
                  type="date"
                  value={botDateFrom}
                  onChange={(e) => setBotDateFrom(e.target.value)}
                  className="whatsapp-input w-full px-3 py-1.5 text-xs"
                  title="From date"
                />
                <input
                  type="date"
                  value={botDateTo}
                  onChange={(e) => setBotDateTo(e.target.value)}
                  className="whatsapp-input w-full px-3 py-1.5 text-xs"
                  title="To date"
                />
              </div>
              <p className="mt-1 text-[11px] text-slate-500">
                {templateSendFilterViewActive
                  ? "Dates filter when the template was logged as sent (UTC day). Clear template filter to use dates for last activity only."
                  : "Dates filter conversations by last activity. For template send log, pick template below and Apply."}
              </p>
              <div className="mt-2 space-y-1">
                <label className="text-[11px] font-medium text-slate-600">Filter by sent template (Smart Messaging log)</label>
                <select
                  value={templateSendFilterId}
                  onChange={(e) => setTemplateSendFilterId(e.target.value)}
                  className="whatsapp-input w-full px-3 py-1.5 text-xs"
                  disabled={templateSendFilterLoading}
                >
                  <option value="">— Select template —</option>
                  {Object.keys(messagingTemplates)
                    .sort()
                    .map((tid) => (
                      <option key={tid} value={tid}>
                        {(messagingTemplates[tid]?.name || tid).slice(0, 80)}
                      </option>
                    ))}
                </select>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={templateSendFilterLoading}
                    onClick={() => applyTemplateSendFilter()}
                    className="text-xs px-2 py-1 rounded border border-violet-200 bg-violet-50 hover:bg-violet-100 text-violet-800 disabled:opacity-50"
                  >
                    {templateSendFilterLoading ? "Loading…" : "Apply template filter"}
                  </button>
                  <button
                    type="button"
                    disabled={templateSendFilterLoading}
                    onClick={() => clearTemplateSendFilter()}
                    className="text-xs px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 text-slate-600"
                  >
                    Clear template filter
                  </button>
                </div>
                {templateSendFilterMeta && templateSendFilterViewActive && (
                  <p className="text-[11px] text-slate-500">
                    Log rows: {templateSendFilterMeta.log_entries_matched ?? "—"} · Distinct phones:{" "}
                    {templateSendFilterMeta.distinct_recipients ?? "—"} · Chats shown:{" "}
                    {templateSendFilterMeta.matched_chats ?? "—"} (scanned {templateSendFilterMeta.index_scanned ?? "—"} index rows)
                  </p>
                )}
              </div>
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const today = new Date().toISOString().slice(0, 10);
                    setBotDateFrom(today);
                    setBotDateTo(today);
                  }}
                  className="text-xs px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 text-slate-600"
                >
                  Today
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setBotDateFrom("");
                    setBotDateTo("");
                  }}
                  className="text-xs px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 text-slate-600"
                >
                  Clear
                </button>
                <button
                  type="button"
                  disabled={rebuildingIndex}
                  onClick={async () => {
                    setRebuildingIndex(true);
                    try {
                      const r = await rebuildLiveChatIndex();
                      if (r?.success) {
                        toast.success(`Index rebuilt (${r.written ?? "?"} conversations)`);
                        const refreshed = await getUnifiedChats("", 1, CHAT_LIST_PAGE_SIZE);
                        if (refreshed?.success && Array.isArray(refreshed.chats)) {
                          applyServerConversations(refreshed.chats);
                          setHasMoreChats(refreshed.has_more ?? false);
                          setNextCursor(refreshed.next_cursor ?? null);
                        }
                      } else {
                        toast.error(r?.error || "Rebuild failed");
                      }
                    } catch (e) {
                      toast.error(errorMessage(e) || "Rebuild failed");
                    } finally {
                      setRebuildingIndex(false);
                    }
                  }}
                  className="text-xs px-2 py-1 rounded border border-amber-200 hover:bg-amber-50 text-amber-700"
                  title="If chats don't show, rebuild index from Firestore"
                >
                  {rebuildingIndex ? "Rebuilding..." : "Rebuild index"}
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const r = await simulateWebhook("9613000000", "Hello");
                      if (r?.success) {
                        toast.success("Test message sent – check Live Chat in a few seconds");
                        setTimeout(async () => {
                          const refreshed = await getUnifiedChats("", 1, CHAT_LIST_PAGE_SIZE);
                          if (refreshed?.success && Array.isArray(refreshed.chats)) {
                            applyServerConversations(refreshed.chats);
                          }
                        }, 2000);
                      } else {
                        toast.error(r?.error || "Simulate failed");
                      }
                    } catch (e) {
                      toast.error(errorMessage(e) || "Simulate failed");
                    }
                  }}
                  className="text-xs px-2 py-1 rounded border border-green-200 hover:bg-green-50 text-green-700"
                  title="Test if message flow works (simulates webhook)"
                >
                  Test flow
                </button>
                {isBotDateFilterActive && !templateSendFilterViewActive && (
                  <span className="text-[11px] text-slate-500">
                    Showing selected range (last activity)
                  </span>
                )}
              </div>
            </div>
            {/* List - scrolls independently below header */}
            <div
              className="flex-1 overflow-y-auto overflow-x-hidden min-h-0 py-3"
              ref={botListRef}
              onScroll={handleBotListScroll}
            >
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
                            key={`${conv.user_id}_${conv.conversation_id}`}
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
                                <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                                  <p className="font-medium text-slate-800 text-sm">
                                    {conv.user_name}
                                  </p>
                                  <span className="inline-block px-2 py-0.5 bg-green-500 text-white text-xs font-bold rounded-full">
                                    Live
                                  </span>
                                  <NewCustomerBadge isNew={conv.is_new_customer} />
                                  {newConversationIds.has(conv.conversation_id) && (
                                    <span className="inline-block px-2 py-0.5 bg-blue-500 text-white text-xs font-bold rounded-full animate-pulse">
                                      New
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-slate-500">
                                  {formatPhoneForDisplay(conv.user_phone || conv.phone_number || "")}
                                </p>
                              </div>
                              <SentimentIndicator sentiment={conv.sentiment} />
                            </div>
                            <div className="mb-2"><StatusBadge status={conv.status} /></div>
                            {(lastMessageContent(conv.last_message) ?? conv.last_message_text) && (
                              <p className="text-xs text-slate-600 truncate mb-1">
                                {lastMessageContent(conv.last_message) ?? conv.last_message_text ?? ""}
                              </p>
                            )}
                            <div className="flex items-center justify-between text-xs text-slate-500">
                              <span>{(conv.message_count ?? 0)} messages</span>
                              <span>
                                {(conv.duration_seconds || 0) > 0
                                  ? `${Math.floor((conv.duration_seconds ?? 0) / 60)}m • `
                                  : ""}
                                {formatConversationListDate(conv)}
                              </span>
                            </div>
                            {conv.template_send_logged_at && (
                              <p className="text-[10px] text-violet-600 mt-1">
                                Sent (logged):{" "}
                                {new Date(conv.template_send_logged_at).toLocaleString()}
                              </p>
                            )}
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
                            key={`${conv.user_id}_${conv.conversation_id}`}
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
                                <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                                  <p className="font-medium text-slate-800 text-sm">
                                    {conv.user_name}
                                  </p>
                                  <NewCustomerBadge isNew={conv.is_new_customer} />
                                  {newConversationIds.has(conv.conversation_id) && (
                                    <span className="inline-block px-2 py-0.5 bg-blue-500 text-white text-xs font-bold rounded-full animate-pulse">
                                      New
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-slate-500">
                                  {formatPhoneForDisplay(conv.user_phone || conv.phone_number || "")}
                                </p>
                              </div>
                              <SentimentIndicator sentiment={conv.sentiment} />
                            </div>
                            <div className="mb-2"><StatusBadge status={conv.status} /></div>
                            {(lastMessageContent(conv.last_message) ?? conv.last_message_text) && (
                              <p className="text-xs text-slate-600 truncate mb-1">
                                {lastMessageContent(conv.last_message) ?? conv.last_message_text ?? ""}
                              </p>
                            )}
                            <div className="flex items-center justify-between text-xs text-slate-500">
                              <span>{(conv.message_count ?? 0)} messages</span>
                              <span>
                                {(conv.duration_seconds || 0) > 0
                                  ? `${Math.floor((conv.duration_seconds ?? 0) / 60)}m • `
                                  : ""}
                                {formatConversationListDate(conv)}
                              </span>
                            </div>
                            {conv.template_send_logged_at && (
                              <p className="text-[10px] text-violet-600 mt-1">
                                Sent (logged):{" "}
                                {new Date(conv.template_send_logged_at).toLocaleString()}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
              {hasMoreChats && !templateSendFilterViewActive && (
                <div className="mt-2">
                  <div ref={botLoadMoreSentinelRef} className="h-2 min-h-[8px]" aria-hidden="true" />
                  <button
                    onClick={loadMoreChats}
                    disabled={loadingMoreChats}
                    className="w-full py-3 text-sm font-medium text-primary-600 hover:bg-primary-50 rounded-lg border border-primary-200 transition disabled:opacity-60"
                  >
                    {loadingMoreChats ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="inline-block w-4 h-4 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
                        Loading...
                      </span>
                    ) : (
                      "Load More"
                    )}
                  </button>
                </div>
              )}
            </div>
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
                        {templateSendFilterViewActive ? (
                          <>
                            Template: {templateSendFilterLabel} ({filteredBotConversations.length})
                          </>
                        ) : (
                          <>With bot ({filteredBotConversations.length})</>
                        )}
                      </h3>
                      <button
                        onClick={() => setBotPanelOpen(false)}
                        className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
                      >
                        <XMarkIcon className="w-5 h-5" />
                      </button>
                    </div>
                    <div
                      ref={botFloatingScrollRef}
                      className="flex-1 overflow-y-auto p-3"
                      onScroll={handleBotListScroll}
                    >
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
                      <div className="grid grid-cols-2 gap-2 mb-2">
                        <input
                          type="date"
                          value={botDateFrom}
                          onChange={(e) => setBotDateFrom(e.target.value)}
                          className="whatsapp-input w-full px-3 py-1.5 text-xs"
                          title="From date"
                        />
                        <input
                          type="date"
                          value={botDateTo}
                          onChange={(e) => setBotDateTo(e.target.value)}
                          className="whatsapp-input w-full px-3 py-1.5 text-xs"
                          title="To date"
                        />
                      </div>
                      <select
                        value={templateSendFilterId}
                        onChange={(e) => setTemplateSendFilterId(e.target.value)}
                        className="whatsapp-input w-full px-2 py-1.5 text-xs mb-2"
                        disabled={templateSendFilterLoading}
                      >
                        <option value="">Template filter…</option>
                        {Object.keys(messagingTemplates)
                          .sort()
                          .map((tid) => (
                            <option key={tid} value={tid}>
                              {(messagingTemplates[tid]?.name || tid).slice(0, 60)}
                            </option>
                          ))}
                      </select>
                      <div className="flex gap-2 mb-3">
                        <button
                          type="button"
                          disabled={templateSendFilterLoading}
                          onClick={() => applyTemplateSendFilter()}
                          className="text-xs px-2 py-1 rounded border border-violet-200 bg-violet-50 text-violet-800 flex-1 disabled:opacity-50"
                        >
                          Apply
                        </button>
                        <button
                          type="button"
                          onClick={() => clearTemplateSendFilter()}
                          className="text-xs px-2 py-1 rounded border border-slate-200 text-slate-600"
                        >
                          Clear
                        </button>
                      </div>
                      <div className="space-y-2">
                        {liveBotConversations.length > 0 && (
                          <div className="pt-1">
                            <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">Live now</p>
                            <div className="space-y-2">
                              {liveBotConversations.map((conv) => (
                                <div
                                  key={`${conv.user_id}_${conv.conversation_id}`}
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
                                    <div className="flex items-center gap-2">
                                    <p className="font-medium text-slate-800 text-sm truncate">{conv.user_name}</p>
                                    <NewCustomerBadge isNew={conv.is_new_customer} />
                                  </div>
                                    <SentimentIndicator sentiment={conv.sentiment} />
                                  </div>
                                  <p className="text-xs text-slate-500 truncate">{formatPhoneForDisplay(conv.user_phone || conv.phone_number || "")}</p>
                                  <p className="text-[11px] text-slate-400 mt-1">{formatConversationListDate(conv)}</p>
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
                                  key={`${conv.user_id}_${conv.conversation_id}`}
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
                                    <div className="flex items-center gap-2">
                                      <p className="font-medium text-slate-800 text-sm truncate">{conv.user_name}</p>
                                      <NewCustomerBadge isNew={conv.is_new_customer} />
                                    </div>
                                    <SentimentIndicator sentiment={conv.sentiment} />
                                  </div>
                                  <p className="text-xs text-slate-500 truncate">{formatPhoneForDisplay(conv.user_phone || conv.phone_number || "")}</p>
                                  <p className="text-[11px] text-slate-400 mt-1">{formatConversationListDate(conv)}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {hasMoreChats && (
                          <button
                            onClick={loadMoreChats}
                            disabled={loadingMoreChats}
                            className="w-full py-2 mt-2 text-sm font-medium text-primary-600 hover:bg-primary-50 rounded-lg border border-primary-200 transition disabled:opacity-60"
                          >
                            {loadingMoreChats ? (
                              <span className="inline-flex items-center gap-2">
                                <span className="inline-block w-4 h-4 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
                                Loading...
                              </span>
                            ) : (
                              "Load More"
                            )}
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
                        With bot ({filteredBotConversations.length})
                      </button>
                    )}
                    <div className="w-10 h-10 bg-gradient-to-r from-primary-400 to-secondary-400 rounded-full flex items-center justify-center text-white font-bold">
                      {(selectedConversation.conversation.user_name || "?").charAt(0)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-bold text-slate-800">
                          {selectedConversation.conversation.user_name}
                        </p>
                        <NewCustomerBadge isNew={selectedConversation.conversation.is_new_customer} />
                      </div>
                      <div className="flex items-center space-x-3 text-xs text-slate-500">
                        <span className="flex items-center">
                          <PhoneIcon className="w-3 h-3 mr-1" />
                          {formatPhoneForDisplay(selectedConversation.conversation.user_phone || selectedConversation.conversation.phone_number || "")}
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

        {/* Conversation Details - Right panel: Waiting + With operator above, User info below */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          className={`${sidebarCollapsed ? "col-span-2" : "col-span-3"} whatsapp-info-panel flex flex-col overflow-y-auto p-4`}
        >
          {/* Waiting for human + With operator - taller blocks above user info */}
          <div className="space-y-3 mb-4 flex-shrink-0">
            <div className="whatsapp-info-card p-4">
              <h3 className="font-semibold text-slate-800 text-sm mb-1 flex items-center">
                <span className="mr-1.5">⏳</span>
                Waiting ({filteredWaitingQueue.length})
              </h3>
              {isLoading ? (
                <div className="animate-pulse h-12 bg-slate-100 rounded" />
              ) : (
                <>
                  <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                    {filteredWaitingQueue.length === 0 ? (
                      <p className="text-xs text-slate-400 italic py-1">None</p>
                    ) : (
                      filteredWaitingQueue.map((item) => {
                        const isUserRequested = userRequestedReasons.includes((item.reason || "").toLowerCase());
                        const readKey = `${item.user_id}_${item.conversation_id}`;
                        const readCount = readMessageCountByConv[readKey] ?? 0;
                        const msgCount = item.message_count || 0;
                        // If locally marked read this session, show 0. Else use API unread_count (user msgs only)
                        const unreadCount =
                          readCount > 0 && readCount >= msgCount
                            ? 0
                            : typeof item.unread_count === "number"
                              ? item.unread_count
                              : Math.max(0, msgCount - readCount);
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
                                last_message:
                                  typeof item.last_message === "string"
                                    ? item.last_message
                                    : item.last_message && typeof item.last_message === "object"
                                      ? {
                                          content:
                                            typeof item.last_message.content === "string"
                                              ? item.last_message.content
                                              : "",
                                        }
                                      : null,
                              };
                              selectConversation(conv);
                            }}
                          >
                            <div className="flex items-center justify-between gap-1">
                              <div className="flex items-center gap-2 min-w-0">
                                <p className="font-medium text-slate-800 truncate">{item.user_name}</p>
                                <NewCustomerBadge isNew={item.is_new_customer} />
                              </div>
                              {unreadCount > 0 && (
                                <span className="text-xs font-bold text-amber-600">{unreadCount}</span>
                              )}
                            </div>
                            <div className="flex items-center justify-between mt-0.5">
                              <span className="text-slate-500">{Math.floor((item.wait_time_seconds || 0) / 60)}m</span>
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
            <div className="whatsapp-info-card p-4">
              <h3 className="font-semibold text-slate-800 text-sm mb-1 flex items-center">
                <span className="mr-1.5">💬</span>
                With operator ({filteredWithOperator.length})
              </h3>
              {isLoading ? (
                <div className="animate-pulse h-10 bg-slate-100 rounded" />
              ) : (
                <>
                  <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                    {filteredWithOperator.length === 0 ? (
                      <p className="text-xs text-slate-400 italic py-1">None</p>
                    ) : (
                      filteredWithOperator.map((conv) => {
                        const readKey = `${conv.user_id}_${conv.conversation_id}`;
                        const readCount = readMessageCountByConv[readKey] ?? 0;
                        const msgCount = conv.message_count || 0;
                        // If locally marked read this session, show 0. Else use API unread_count (user msgs only)
                        const unreadCount =
                          readCount > 0 && readCount >= msgCount
                            ? 0
                            : typeof conv.unread_count === "number"
                              ? conv.unread_count
                              : Math.max(0, msgCount - readCount);
                        return (
                          <div
                            key={`${conv.user_id}_${conv.conversation_id}`}
                            className="px-2 py-1.5 rounded cursor-pointer bg-green-50 border border-green-200 hover:bg-green-100 transition-colors text-xs flex items-center justify-between"
                            onClick={() => selectConversation(conv)}
                          >
                            <div className="min-w-0 flex-1 pr-2">
                              <span className="font-medium text-slate-800 truncate block">{conv.user_name}</span>
                              <NewCustomerBadge isNew={conv.is_new_customer} />
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              {unreadCount > 0 && (
                                <span className="inline-flex min-w-[18px] h-[18px] items-center justify-center rounded-full bg-emerald-600 px-1 text-[10px] font-bold text-white">
                                  {unreadCount}
                                </span>
                              )}
                              <SentimentIndicator sentiment={conv.sentiment} />
                            </div>
                          </div>
                        );
                      })
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
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-slate-800">
                        {selectedConversation.conversation.user_name}
                      </p>
                      <NewCustomerBadge isNew={selectedConversation.conversation.is_new_customer} />
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Phone</p>
                    <p className="font-medium text-slate-800">
                      {formatPhoneForDisplay(selectedConversation.conversation.user_phone)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Language</p>
                    <p className="font-medium text-slate-800">
                      {(selectedConversation.conversation.language || "").toUpperCase()}
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
                      {(() => {
                        const durationSeconds =
                          Number(selectedConversation.conversation.duration_seconds) || 0;
                        return `${Math.floor(durationSeconds / 60)}m ${durationSeconds % 60}s`;
                      })()}
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

      {sharedOverlayModals}
    </div>
    </>
  );
};

export default LiveChat;
