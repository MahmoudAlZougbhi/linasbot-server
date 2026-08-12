import { useState, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useOperatorStatus } from "../contexts/OperatorStatusContext";
import { useAuth } from "../contexts/AuthContext";

/** @param {{ mobile?: boolean }} args */
export function useLiveChatShared({ mobile = false }) {
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
  const [readMessageCountByConv, setReadMessageCountByConv] = useState(/** @type {Record<string, number>} */ ({}));
  const [isReleasing, setIsReleasing] = useState(false);
  const releasingRef = useRef(false);
  const sendingRef = useRef(false);
  const [editContent, setEditContent] = useState("");
  const [isSubmittingEdit, setIsSubmittingEdit] = useState(false);
  const [faqContext, setFaqContext] = useState(/** @type {LiveChatFaqContext | null} */ (null));
  const [faqEditAnswer, setFaqEditAnswer] = useState("");
  const [faqContextLoading, setFaqContextLoading] = useState(false);
  const [faqSubmitting, setFaqSubmitting] = useState(false);
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
  const messagesLoadingStartRef = useRef(/** @type {number | null} */ (null));

  const {
    getUnifiedChats, getChatsByTemplateSendLog, getLiveConversations, getWaitingQueue,
    rebuildLiveChatIndex, simulateWebhook, getConversationMessages, takeoverConversation,
    releaseConversation, sendOperatorMessage, updateOperatorStatus, submitFeedback,
  } = useApi();

  return {
    isMobileView, searchParams, authUser, operatorId,
    operatorStatus, waitingSearchTerm, activeConversations, setActiveConversations,
    selectedConversation, setSelectedConversation, waitingQueue, setWaitingQueue,
    messageInput, setMessageInput, isLoading, setIsLoading,
    useMockData, setUseMockData, feedbackModal, setFeedbackModal,
    editMessageModal, setEditMessageModal, faqCorrectionModal, setFaqCorrectionModal,
    lastRefreshTime, setLastRefreshTime, newConversationIds, setNewConversationIds,
    isRefreshing, setIsRefreshing, isSending, setIsSending,
    messagesLoading, setMessagesLoading, loadingMoreMessages, setLoadingMoreMessages,
    hasMoreMessages, setHasMoreMessages, liveSearchQuery, setLiveSearchQuery,
    debouncedSearch, setDebouncedSearch, botDateFrom, setBotDateFrom,
    botDateTo, setBotDateTo, templateSendFilterId, setTemplateSendFilterId,
    templateSendFilterActive, setTemplateSendFilterActive, templateSendFilterChats, setTemplateSendFilterChats,
    templateSendFilterMeta, setTemplateSendFilterMeta, templateSendFilterLoading, setTemplateSendFilterLoading,
    messagingTemplates, setMessagingTemplates, setChatPage, nextCursor,
    setNextCursor, hasMoreChats, setHasMoreChats, loadingMoreChats,
    setLoadingMoreChats, rebuildingIndex, setRebuildingIndex, sidebarCollapsed,
    setSidebarCollapsed, botPanelOpen, setBotPanelOpen, mobileListSection,
    setMobileListSection, mobileDetailsOpen, setMobileDetailsOpen, mobileFilterSheetOpen,
    setMobileFilterSheetOpen, readMessageCountByConv, setReadMessageCountByConv, isReleasing,
    setIsReleasing, releasingRef, sendingRef, editContent,
    setEditContent, isSubmittingEdit, setIsSubmittingEdit, faqContext,
    setFaqContext, faqEditAnswer, setFaqEditAnswer, faqContextLoading,
    setFaqContextLoading, faqSubmitting, setFaqSubmitting, messagesContainerRef,
    messagesEndRef, selectedConversationRef, activeConversationsRef, waitingQueueRef,
    cachedActiveConversationsRef, cachedWaitingQueueRef, useMockDataRef, debouncedSearchRef,
    isMountedRef, previousConversationIdRef, previousMessageCountRef, forceBottomOnOpenRef,
    messageCacheRef, hasMoreMessagesRef, autoLoadedPagesRef, botListRef,
    botLoadMoreSentinelRef, botListScrollThrottleRef, botFloatingScrollRef, loadMoreInProgressRef,
    loadMoreCooldownUntilRef, messagesLoadingStartRef, getUnifiedChats, getChatsByTemplateSendLog,
    getLiveConversations, getWaitingQueue, rebuildLiveChatIndex, simulateWebhook,
    getConversationMessages, takeoverConversation, releaseConversation, sendOperatorMessage,
    updateOperatorStatus, submitFeedback,
  };
}
