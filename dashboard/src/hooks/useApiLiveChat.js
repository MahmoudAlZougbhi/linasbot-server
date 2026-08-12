import { useCallback } from "react";
import toast from "react-hot-toast";
import { normalizeConversationMessages } from "../utils/liveChatApi";
import { errorMessage, getAxiosErrorCode, getAxiosResponseDetail } from "../utils/apiValidate";
import { api } from "./useApiClient";

/** @param {{ setLoading: Function }} args */
export function useApiLiveChat({ setLoading }) {
  // Live Chat API functions - WhatsApp-style: unified chats (live + history)
  // cursor: use for Load More (backend uses cursor-based pagination, not page offset)
  const getUnifiedChats = useCallback(
    /**
     * @param {string} [search]
     * @param {number} [page]
     * @param {number} [pageSize]
     * @param {string | null} [cursor]
     */
    async (search = "", page = 1, pageSize = 30, cursor = null) => {
    try {
      const params = new URLSearchParams();
      if (search && search.trim()) params.append("search", search.trim());
      params.append("page", String(page));
      params.append("page_size", String(pageSize));
      if (cursor && typeof cursor === "string") params.append("cursor", cursor);
      const response = await api.get(`/api/live-chat/unified-chats?${params.toString()}`, {
        timeout: 30000,
      });
      const data = response?.data || {};
      const chats = Array.isArray(data.chats)
        ? data.chats
        : Array.isArray(data.conversations)
          ? data.conversations
          : [];
      const total = typeof data.total === "number" ? data.total : chats.length;
      const hasMore = typeof data.has_more === "boolean"
        ? data.has_more
        : typeof data.hasMore === "boolean"
          ? data.hasMore
          : total > (page * pageSize);

      return {
        ...data,
        success: data.success !== false,
        chats,
        total,
        has_more: hasMore,
        next_cursor: data.next_cursor || null,
      };
    } catch (error) {
      const code = getAxiosErrorCode(error);
      if (code === "ERR_NETWORK" || code === "ECONNABORTED") {
        return { success: false, chats: [], total: 0, has_more: false, error: code === "ECONNABORTED" ? "Request timeout" : "Backend offline" };
      }
      throw error;
    }
    },
    []
  );

  const getSmartMessagingTemplates = useCallback(async () => {
    try {
      const response = await api.get("/api/smart-messaging/templates", { timeout: 20000 });
      return response.data;
    } catch (error) {
      const code = getAxiosErrorCode(error);
      if (code === "ERR_NETWORK" || code === "ECONNABORTED") {
        return { success: false, templates: {}, error: "Backend offline" };
      }
      return { success: false, templates: {}, error: errorMessage(error) };
    }
  }, []);

  const getChatsByTemplateSendLog = useCallback(async (/** @type {string} */ templateId, dateFrom = "", dateTo = "") => {
    try {
      const params = new URLSearchParams();
      params.append("template_id", String(templateId || "").trim());
      if (dateFrom) params.append("date_from", dateFrom);
      if (dateTo) params.append("date_to", dateTo);
      const response = await api.get(`/api/live-chat/chats-by-template-send-log?${params.toString()}`, {
        timeout: 90000,
      });
      return response.data;
    } catch (error) {
      const code = getAxiosErrorCode(error);
      if (code === "ERR_NETWORK" || code === "ECONNABORTED") {
        return {
          success: false,
          chats: [],
          error: code === "ECONNABORTED" ? "Request timeout" : "Backend offline",
        };
      }
      throw error;
    }
  }, []);

  const getLiveConversations = useCallback(async (search = "") => {
    try {
      const params = new URLSearchParams();
      if (search && search.trim()) params.append("search", search.trim());
      const query = params.toString();
      const url = query ? `/api/live-chat/active-conversations?${query}` : "/api/live-chat/active-conversations";
      const response = await api.get(url, {
        timeout: 25000,
      });
      return response.data;
    } catch (error) {
      const code = getAxiosErrorCode(error);
      if (code === "ERR_NETWORK" || code === "ECONNABORTED") {
        return { success: false, conversations: [], error: code === "ECONNABORTED" ? "Request timeout" : "Backend offline" };
      }
      throw error;
    }
  }, []);

  const getWaitingQueue = useCallback(async () => {
    try {
      const response = await api.get("/api/live-chat/waiting-queue", {
        timeout: 15000,
      });
      return response.data;
    } catch (error) {
      const code = getAxiosErrorCode(error);
      if (code === "ERR_NETWORK" || code === "ECONNABORTED") {
        return {
          success: false,
          queue: [],
          error: code === "ECONNABORTED" ? "Request timeout" : "Backend offline",
        };
      }
      throw error;
    }
  }, []);

  const getLiveChatStatus = useCallback(async () => {
    try {
      const response = await api.get("/api/live-chat/status", { timeout: 5000 });
      return response.data;
    } catch {
      return { success: false, index_count: 0, users_count: 0 };
    }
  }, []);

  const rebuildLiveChatIndex = useCallback(async () => {
    const response = await api.post("/api/live-chat/rebuild-index", null, { timeout: 60000 });
    return response.data;
  }, []);

  const simulateWebhook = useCallback(async (phone = "9613000000", text = "Hello") => {
    const response = await api.post("/api/debug/simulate-webhook", { phone, text }, { timeout: 15000 });
    return response.data;
  }, []);

  /** Same axios as getUnifiedChats – use for loading conversation messages so request goes to same origin. */
  const getConversationMessages = useCallback(
    /**
     * @param {string} userId
     * @param {string} conversationId
     * @param {number} [days]
     * @param {string | null} [before]
     * @param {number} [day_window]
     * @param {number} [limit]
     */
    async (userId, conversationId, days = 0, before = null, day_window = 0, limit = 50) => {
      try {
        const params = new URLSearchParams();
        if (days > 0) params.append("days", String(days));
        if (before) params.append("before", before);
        if (day_window > 0) params.append("day_window", String(day_window));
        params.append("limit", String(Math.min(100, Math.max(1, limit))));
        const response = await api.get(
          `/api/live-chat/conversation/${encodeURIComponent(userId)}/${encodeURIComponent(conversationId)}?${params.toString()}`,
          { timeout: 8000 }
        );
        const data = response.data;
        if (!data.success) {
          throw new Error(data.error || "Failed to load messages");
        }
        const messages = Array.isArray(data.messages)
          ? normalizeConversationMessages(data.messages)
          : [];
        return { messages, hasMore: data.has_more ?? false };
      } catch (error) {
        const code = getAxiosErrorCode(error);
        if (code === "ERR_NETWORK") {
          throw new Error("Backend offline – cannot load messages");
        }
        if (code === "ECONNABORTED") {
          throw new Error("Loading messages timed out - try again");
        }
        throw error;
      }
    },
    []
  );

  const takeoverConversation = useCallback(
    /**
     * @param {string} conversationId
     * @param {string} userId
     * @param {string} operatorId
     */
    async (conversationId, userId, operatorId) => {
      try {
        setLoading(true);
        console.log("📞 Takeover request:", { conversationId, userId, operatorId });
        const response = await api.post("/api/live-chat/takeover", {
          conversation_id: conversationId,
          user_id: userId,
          operator_id: operatorId,
        }, {
          timeout: 60000, // 60 seconds - Firestore operations can be slow
        });
        toast.success("Conversation taken over successfully!");
        return response.data;
      } catch (error) {
        console.error("❌ Takeover error:", error);
        const code = getAxiosErrorCode(error);
        if (code === "ERR_NETWORK") {
          toast.error("Backend offline - cannot take over conversation");
          return { success: false, error: "Backend offline" };
        }
        if (code === "ECONNABORTED") {
          toast.error("Takeover timed out - please try again");
          return { success: false, error: "timeout of 60000ms exceeded" };
        }
        // Show actual error message from server
        const errorMsg = getAxiosResponseDetail(error) || errorMessage(error) || "Unknown error";
        toast.error(`Takeover failed: ${errorMsg}`);
        return { success: false, error: errorMsg };
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const releaseConversation = useCallback(async (/** @type {string} */ conversationId, /** @type {string} */ userId) => {
    try {
      setLoading(true);
      const response = await api.post("/api/live-chat/release", {
        conversation_id: conversationId,
        user_id: userId,
      }, {
        timeout: 60000, // 60 seconds - Firestore operations can be slow
      });
      // Toast shown by caller (LiveChat) to avoid duplicates
      return response.data;
    } catch (error) {
      const code = getAxiosErrorCode(error);
      if (code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot release conversation");
        return { success: false, error: "Backend offline" };
      }
      if (code === "ECONNABORTED") {
        toast.error("Release timed out - please try again");
        return { success: false, error: "timeout" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const sendOperatorMessage = useCallback(
    /**
     * @param {string} conversationId
     * @param {string} userId
     * @param {string} message
     * @param {string} operatorId
     * @param {string} [messageType]
     * @param {string | null} [idempotencyKey]
     */
    async (
      conversationId,
      userId,
      message,
      operatorId,
      messageType = "text",
      idempotencyKey = null
    ) => {
      try {
        setLoading(true);
        const idem =
          idempotencyKey ||
          (typeof crypto !== "undefined" && crypto.randomUUID
            ? crypto.randomUUID()
            : `idem_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`);
        const response = await api.post("/api/live-chat/send-message", {
          conversation_id: conversationId,
          user_id: userId,
          message,
          operator_id: operatorId,
          message_type: messageType,
          idempotency_key: idem,
        }, {
          timeout: 60000, // 60 seconds - Firestore + WhatsApp operations can be slow
        });
        // Toast: callers (e.g. LiveChat) show context-specific success to avoid double toasts
        return response.data;
      } catch (error) {
        const code = getAxiosErrorCode(error);
        if (code === "ERR_NETWORK") {
          toast.error("Backend offline - cannot send message");
          return { success: false, error: "Backend offline" };
        }
        if (code === "ECONNABORTED") {
          toast.error("Message send timed out - please try again");
          return { success: false, error: "timeout" };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const updateOperatorStatus = useCallback(async (/** @type {string} */ operatorId, /** @type {string} */ status) => {
    try {
      const response = await api.post("/api/live-chat/operator-status", {
        operator_id: operatorId,
        status,
      });
      return response.data;
    } catch (error) {
      const code = getAxiosErrorCode(error);
      if (code === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      throw error;
    }
  }, []);

  const getLiveChatMetrics = useCallback(async () => {
    try {
      const response = await api.get("/api/live-chat/metrics");
      return response.data;
    } catch (error) {
      const code = getAxiosErrorCode(error);
      if (code === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      throw error;
    }
  }, []);


  return {
    getUnifiedChats,
    getSmartMessagingTemplates,
    getChatsByTemplateSendLog,
    getLiveConversations,
    getWaitingQueue,
    getLiveChatStatus,
    rebuildLiveChatIndex,
    simulateWebhook,
    getConversationMessages,
    takeoverConversation,
    releaseConversation,
    sendOperatorMessage,
    updateOperatorStatus,
    getLiveChatMetrics,
  };
}
