import { useState, useCallback } from "react";
import axios from "axios";
import toast from "react-hot-toast";
import { getApiBaseUrl } from "../utils/apiBaseUrl";
import { normalizeConversationMessages } from "../utils/liveChatApi";
import { getCsrfToken } from "../utils/csrf";
import {
  errorMessage,
  getAxiosErrorCode,
  getAxiosResponseDetail,
  isAxiosLikeError,
  isPlainObject,
} from "../utils/apiValidate";

/** @param {string} message */
const toastInfo = (message) => {
  toast(message, { icon: "ℹ️" });
};

// Create axios instance with default config
const api = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 90000, // 90 seconds - increased for slow GPT responses
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor — refresh base URL each call (fixes stale baseURL if env/hostname logic changes)
api.interceptors.request.use(
  (config) => {
    config.baseURL = getApiBaseUrl();
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      config.headers["X-CSRF-Token"] = csrfToken;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    const code = isAxiosLikeError(error) ? error.code : undefined;
    // Handle network errors gracefully (silent)
    if (code === "ERR_NETWORK") {
      // Silent - no console logs for network errors
      if (process.env.NODE_ENV === "development") {
        return Promise.reject(error);
      }
    }

    // Handle timeout errors gracefully (silent)
    if (code === "ECONNABORTED") {
      // Silent - no console logs for timeout errors
      return Promise.reject(error);
    }

    // 504 Gateway Timeout - let the calling component show a friendly message
    if (isAxiosLikeError(error) && error.response?.status === 504) {
      return Promise.reject(error);
    }

    if (isAxiosLikeError(error) && error.response?.status === 401) {
      localStorage.removeItem("auth_session");
      localStorage.removeItem("csrf_token");
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
      return Promise.reject(error);
    }

    const responseData =
      isAxiosLikeError(error) && isPlainObject(error.response?.data)
        ? error.response.data
        : undefined;
    const message =
      (typeof responseData?.message === "string" ? responseData.message : undefined) ||
      (isAxiosLikeError(error) ? error.message : undefined) ||
      errorMessage(error) ||
      "An error occurred";

    // Only show toast for non-network and non-timeout errors
    if (code !== "ERR_NETWORK" && code !== "ECONNABORTED") {
      toast.error(message);
    }

    return Promise.reject(error);
  }
);

export const useApi = () => {
  const [loading, setLoading] = useState(false);
  const [currentProvider, setCurrentProvider] = useState("meta");
  const [botStatus, setBotStatus] = useState(/** @type {BotStatus} */ ({
    status: "unknown",
    uptime: 0,
    responseTime: 0,
    features: [],
    currentProvider: "meta",
  }));

  // Fetch bot status
  const fetchBotStatus = useCallback(async () => {
    try {
      setLoading(true);
      // Use shorter timeout for initial status check
      const response = await api.get("/api/test", {
        timeout: 5000, // 5 seconds - don't block login/dashboard load
      });
      setBotStatus({
        status: "online",
        uptime: Date.now(),
        responseTime: 2.1,
        features: response.data.features || [],
        ...response.data,
      });
      return response.data;
    } catch (error) {
      const code = getAxiosErrorCode(error);
      // Set offline status but don't throw error for network/timeout issues
      setBotStatus({
        status: code === "ECONNABORTED" ? "slow" : "offline",
        uptime: 0,
        responseTime: 0,
        features: [],
      });

      // Only throw non-network and non-timeout errors
      if (code !== "ERR_NETWORK" && code !== "ECONNABORTED") {
        throw error;
      }

      // Return mock data for network/timeout errors
      return {
        status: code === "ECONNABORTED" ? "slow" : "offline",
        message: code === "ECONNABORTED"
          ? "Backend is slow but running"
          : "Backend not available - using mock data",
        features: [
          "Text Chat",
          "Voice Processing",
          "Image Analysis",
          "Q&A Management",
        ],
      };
    } finally {
      setLoading(false);
    }
  }, []);

  // Test text message
  const testTextMessage = useCallback(
    /**
     * @param {string} message
     * @param {string} [language]
     * @param {string} [userPhone]
     */
    async (message, language = "auto", userPhone = "") => {
      try {
        setLoading(true);
        const response = await api.post("/api/test-text", {
          message,
          language,
          userPhone,
          timestamp: Date.now(),
        });
        toast.success("Text message processed successfully!");
        return response.data;
      } catch (error) {
        const code = getAxiosErrorCode(error);
        // Handle network error with mock response
        if (code === "ERR_NETWORK") {
          toastInfo("Backend offline - showing mock response");
          return {
            success: true,
            input: message,
            response:
              "This is a mock response. The backend server is not running. Start the bot backend to get real responses.",
            detected_language: language,
            mode: "mock",
            user_phone: userPhone,
            response_time_ms: 100,
            timestamp: Date.now(),
          };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // Test voice transcription
  const testVoiceTranscription = useCallback(
    /**
     * @param {File | Blob} audioFile
     * @param {string} provider
     * @param {string} userPhone
     */
    async (audioFile, provider, userPhone) => {
      try {
        setLoading(true);
        const formData = new FormData();
        formData.append("audio", audioFile);
        formData.append("phone", userPhone || "123456789");
        formData.append("provider", provider || currentProvider);
        formData.append("timestamp", String(Date.now()));

        const response = await api.post("/api/test-voice", formData, {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        });

        toast.success("Voice message processed!");
        return response.data;
      } finally {
        setLoading(false);
      }
    },
    [currentProvider]
  );

  // Test image analysis (file upload)
  const testImageAnalysis = useCallback(
    /**
     * @param {File | Blob} imageFile
     * @param {string} provider
     * @param {string} userPhone
     */
    async (imageFile, provider, userPhone) => {
      try {
        setLoading(true);
        const formData = new FormData();
        formData.append("image", imageFile);
        formData.append("phone", userPhone || "123456789");
        formData.append("provider", provider || currentProvider);
        formData.append("caption", "");

        const response = await api.post("/api/test-image-upload", formData, {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        });

        toast.success("Image analysis completed!");
        return response.data;
      } catch (error) {
        const code = getAxiosErrorCode(error);
        // Handle network error with mock response
        if (code === "ERR_NETWORK") {
          toastInfo("Backend offline - showing mock response");
          return {
            success: true,
            bot_response:
              "Mock image analysis: This appears to be a tattoo that can be removed with laser treatment. Estimated 6-8 sessions needed.",
            response_time_ms: 1500,
            analysis: "Mock analysis result",
          };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    },
    [currentProvider]
  );

  // Test image analysis with URL (new endpoint)
  const testImageWithUrl = useCallback(
    /**
     * @param {string} imageUrl
     * @param {string} [caption]
     * @param {string} [provider]
     * @param {string} [userPhone]
     */
    async (
      imageUrl,
      caption = "",
      provider = currentProvider,
      userPhone = ""
    ) => {
      try {
        setLoading(true);
        const response = await api.post("/api/test-image", {
          phone: userPhone || "123456789",
          image_url: imageUrl,
          caption,
          provider,
        });
        toast.success("Image analysis completed!");
        return response.data;
      } catch (error) {
        const code = getAxiosErrorCode(error);
        // Handle network error with mock response
        if (code === "ERR_NETWORK") {
          toastInfo("Backend offline - showing mock response");
          return {
            success: true,
            bot_response: `Mock image analysis from ${provider}: This appears to be a tattoo. ${
              caption ? `Caption: ${caption}` : ""
            }`,
            response_time_ms: 1500,
            provider,
          };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    },
    [currentProvider]
  );

  // Test voice message with text (new endpoint)
  const testVoiceWithText = useCallback(
    /**
     * @param {string} voiceText
     * @param {string} [provider]
     * @param {string} [userPhone]
     */
    async (voiceText, provider = currentProvider, userPhone = "") => {
      try {
        setLoading(true);
        const response = await api.post("/api/test-voice-text", {
          phone: userPhone || "123456789",
          voice_text: voiceText,
          provider,
        });
        toast.success("Voice message processed!");
        return response.data;
      } catch (error) {
        const code = getAxiosErrorCode(error);
        // Handle network error with mock response
        if (code === "ERR_NETWORK") {
          toastInfo("Backend offline - showing mock response");
          return {
            success: true,
            bot_response: `Mock voice response from ${provider}: I heard you say "${voiceText}". Here's my response...`,
            response_time_ms: 800,
            provider,
          };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    },
    [currentProvider]
  );

  // Training functions
  const addTrainingData = useCallback(
    /**
     * @param {string} question
     * @param {string} answer
     * @param {string} [language]
     */
    async (question, answer, language = "ar") => {
      try {
        setLoading(true);
        const response = await api.post("/api/training/add", {
          question,
          answer,
          language,
          timestamp: Date.now(),
        });

        toast.success("Training data added successfully!");
        return response.data;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const getTrainingData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get("/api/training/list");
      return response.data;
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteTrainingData = useCallback(async (/** @type {string} */ id) => {
    try {
      setLoading(true);
      const response = await api.delete(`/api/training/${id}`);
      toast.success("Training data deleted successfully!");
      return response.data;
    } finally {
      setLoading(false);
    }
  }, []);

  // Search training data
  const searchTrainingData = useCallback(async (/** @type {string} */ query) => {
    try {
      setLoading(true);
      const response = await api.post("/api/training/search", {
        query,
        timestamp: Date.now(),
      });
      return response.data;
    } finally {
      setLoading(false);
    }
  }, []);

  // Provider switching
  const switchProvider = useCallback(async (/** @type {string} */ provider) => {
    try {
      setLoading(true);
      const response = await api.post("/api/switch-provider", {
        provider,
      });

      setCurrentProvider(provider);
      setBotStatus((prev) => ({
        ...prev,
        currentProvider: provider,
      }));

      toast.success(`Switched to ${provider}`);
      return response.data;
    } catch (error) {
      const code = getAxiosErrorCode(error);
      // Handle network error gracefully
      if (code === "ERR_NETWORK") {
        setCurrentProvider(provider);
        setBotStatus((prev) => ({
          ...prev,
          currentProvider: provider,
        }));
        toastInfo(`Switched to ${provider} (offline mode)`);
        return { success: true, provider };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  // Test message with provider (optional channel=instagram|facebook for Meta parity)
  const testMessageWithProvider = useCallback(
    /**
     * @param {string} message
     * @param {string} [provider]
     * @param {string} [userPhone]
     * @param {"instagram" | "facebook" | null} [channel]
     */
    async (message, provider = currentProvider, userPhone = "", channel = null) => {
      try {
        setLoading(true);
        /** @type {TestMessagePayload} */
        const payload = {
          phone: userPhone || "123456789",
          message,
          provider,
        };
        if (channel === "instagram" || channel === "facebook") {
          payload.channel = channel;
        }
        const response = await api.post("/api/test-message", payload);
        const data = response.data || {};
        if (data.simulation || data.parity_mode === "meta_social") {
          toast.success("Simulated Meta social path (no external Graph send)");
        } else {
          toast.success("Message processed successfully!");
        }
        return data;
      } catch (error) {
        const code = getAxiosErrorCode(error);
        // Never fake a green bot reply when the backend is offline
        if (code === "ERR_NETWORK") {
          toast.error("Backend offline — cannot run Testing Lab");
          return {
            success: false,
            error: "Backend offline",
            bot_response: "",
            provider,
          };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    },
    [currentProvider]
  );

  // Test webhook simulation (full webhook flow)
  const testWebhookSimulation = useCallback(
    /**
     * @param {string} message
     * @param {string} [provider]
     * @param {string} [userPhone]
     */
    async (message, provider = currentProvider, userPhone = "") => {
      try {
        setLoading(true);
        const response = await api.post("/api/test-webhook", {
          phone: userPhone || "123456789",
          message,
          provider,
        });
        toast.success("Webhook simulation completed!");
        return response.data;
      } catch (error) {
        const code = getAxiosErrorCode(error);
        // Handle network error with mock response
        if (code === "ERR_NETWORK") {
          toastInfo("Backend offline - showing mock response");
          return {
            success: true,
            bot_response: `Mock webhook response from ${provider}: ${message}`,
            response_time_ms: 100,
            provider,
            webhook_payload: { mock: true },
          };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    },
    [currentProvider]
  );

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

  // ✨ NEW: Q&A Management Functions
  const getQAPairs = useCallback(async (/** @type {QAFilters} */ filters = {}) => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filters.category) params.append("category", filters.category);
      if (filters.language) params.append("language", filters.language);
      if (filters.query) params.append("query", filters.query);
      if (filters.active_only !== undefined)
        params.append("active_only", String(filters.active_only));

      const response = await api.get(`/api/qa/list?${params}`);
      return response.data;
    } catch (error) {
      const code = getAxiosErrorCode(error);
      if (code === "ERR_NETWORK") {
        console.log("Backend offline - Q&A using mock data");
        return {
          success: false,
          data: [],
          error: "Backend offline",
          message: "Backend not available",
        };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const createQAPair = useCallback(async (/** @type {Record<string, unknown>} */ qaData) => {
    try {
      setLoading(true);
      const response = await api.post("/api/qa/create", qaData);
      toast.success("Q&A pair created successfully!");
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot create Q&A pair");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const updateQAPair = useCallback(async (/** @type {string} */ qaId, /** @type {Record<string, unknown>} */ updates) => {
    try {
      setLoading(true);
      const response = await api.put(`/api/qa/${qaId}`, updates);
      toast.success("Q&A pair updated successfully!");
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot update Q&A pair");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteQAPair = useCallback(async (/** @type {string} */ qaId) => {
    try {
      setLoading(true);
      const response = await api.delete(`/api/qa/${qaId}`);
      toast.success("Q&A pair deleted successfully!");
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot delete Q&A pair");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const testQAMatch = useCallback(async (/** @type {string} */ question, language = "ar") => {
    try {
      setLoading(true);
      const response = await api.post("/api/qa/test-match", {
        question,
        language,
      });
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot test Q&A match");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const getQAStatistics = useCallback(async () => {
    try {
      const response = await api.get("/api/qa/statistics");
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return {
          success: false,
          error: "Backend offline",
          stats: {
            total_qa_pairs: 0,
            active_qa_pairs: 0,
            total_usage: 0,
            match_rate: 0,
          },
        };
      }
      throw error;
    }
  }, []);

  const getQACategories = useCallback(async () => {
    try {
      const response = await api.get("/api/qa/categories");
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return {
          success: false,
          categories: [
            "general",
            "pricing",
            "services",
            "appointments",
            "medical",
          ],
        };
      }
      throw error;
    }
  }, []);

  const rewriteAnswer = useCallback(
    /**
     * @param {string} answer
     * @param {string} [language]
     * @param {string} [context]
     */
    async (answer, language = "ar", context = "beauty/laser center") => {
      try {
        setLoading(true);
        const response = await api.post("/api/qa/rewrite-answer", {
          answer,
          language,
          context,
        });
        return response.data;
      } catch (error) {
        if (getAxiosErrorCode(error) === "ERR_NETWORK") {
          toast.error("Backend offline - cannot rewrite answer");
          return {
            success: false,
            error: "Backend offline",
            original: answer,
            rewritten: answer,
          };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const translateQAPair = useCallback(
    /**
     * @param {string} question
     * @param {string} answer
     * @param {string} [sourceLanguage]
     */
    async (question, answer, sourceLanguage = "ar") => {
      try {
        setLoading(true);
        const response = await api.post("/api/qa/translate", {
          question,
          answer,
          source_language: sourceLanguage,
        });
        return response.data;
      } catch (error) {
        if (getAxiosErrorCode(error) === "ERR_NETWORK") {
          toast.error("Backend offline - cannot translate Q&A pair");
          return { success: false, error: "Backend offline" };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // ✨ NEW: Local Q&A Management Functions (JSON file-based)
  const getLocalQAPairs = useCallback(async (/** @type {QAFilters} */ filters = {}) => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filters.language) params.append("language", filters.language);
      const query = params.toString();
      const endpoint = query
        ? `/api/local-qa/list?${query}`
        : "/api/local-qa/list";
      const response = await api.get(endpoint);
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        console.log("Backend offline - Local Q&A using mock data");
        return {
          success: false,
          data: [],
          error: "Backend offline",
        };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const createLocalQAPair = useCallback(async (/** @type {Record<string, unknown>} */ qaData) => {
    try {
      setLoading(true);
      const response = await api.post("/api/local-qa/create", qaData);
      if (response.data.success) {
        toast.success("Q&A pair saved to local file!");
      }
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot save Q&A pair");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const updateLocalQAPair = useCallback(async (/** @type {string} */ qaId, /** @type {Record<string, unknown>} */ updates) => {
    try {
      setLoading(true);
      const response = await api.put(`/api/local-qa/${qaId}`, updates);
      if (response.data.success) {
        toast.success("Q&A pair updated!");
      }
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot update Q&A pair");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteLocalQAPair = useCallback(async (/** @type {string} */ qaId) => {
    try {
      setLoading(true);
      const response = await api.delete(`/api/local-qa/${qaId}`);
      if (response.data.success) {
        toast.success("Q&A pair deleted!");
      }
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot delete Q&A pair");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const getLocalQAStatistics = useCallback(async () => {
    try {
      const response = await api.get("/api/local-qa/statistics");
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return {
          success: false,
          error: "Backend offline",
          statistics: {
            total: 0,
            by_language: {},
            by_category: {},
          },
        };
      }
      throw error;
    }
  }, []);

  // ✨ NEW: Feedback functions
  const submitFeedback = useCallback(async (/** @type {Record<string, unknown>} */ feedbackData) => {
    try {
      setLoading(true);
      const response = await api.post("/api/feedback/submit", feedbackData);

      if (response.data.success) {
        toast.success("Feedback submitted successfully!");
        if (response.data.training_result?.success) {
          if (feedbackData.feedback_type === "save_to_faq") {
            toast.success("🎓 Saved to FAQ in 4 languages!");
          } else {
            toast.success("🎓 Bot trained with correct answer!");
          }
        }
      }

      return response.data;
    } catch (error) {
      console.error("Error submitting feedback:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot submit feedback");
        return { success: false, error: "Backend offline" };
      }
      toast.error("Failed to submit feedback");
      return { success: false, error: errorMessage(error) };
    } finally {
      setLoading(false);
    }
  }, []);

  const getFeedbackStats = useCallback(async () => {
    try {
      const response = await api.get("/api/feedback/stats");
      return response.data;
    } catch (error) {
      console.error("Error getting feedback stats:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return {
          success: false,
          error: "Backend offline",
          stats: {
            total_feedback: 0,
            good: 0,
            wrong: 0,
            inappropriate: 0,
            unclear: 0,
            trained_count: 0,
          },
        };
      }
      return { success: false, error: errorMessage(error) };
    }
  }, []);

  const getWrongAnswers = useCallback(async (limit = 20) => {
    try {
      const response = await api.get(
        `/api/feedback/wrong-answers?limit=${limit}`
      );
      return response.data;
    } catch (error) {
      console.error("Error getting wrong answers:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", wrong_answers: [] };
      }
      return { success: false, error: errorMessage(error) };
    }
  }, []);

  // ✨ NEW: Training Files Management functions (Knowledge Base, Style Guide, Price List)
  const getTrainingFiles = useCallback(async () => {
    try {
      const response = await api.get("/api/training-files/list");
      return response.data;
    } catch (error) {
      console.error("Error getting training files:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", files: [] };
      }
      return { success: false, error: errorMessage(error) };
    }
  }, []);

  const getTrainingFile = useCallback(async (/** @type {string} */ fileId) => {
    try {
      setLoading(true);
      const response = await api.get(`/api/training-files/${fileId}`);
      return response.data;
    } catch (error) {
      console.error(`Error getting training file ${fileId}:`, error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: errorMessage(error) };
    } finally {
      setLoading(false);
    }
  }, []);

  const updateTrainingFile = useCallback(async (/** @type {string} */ fileId, /** @type {string} */ content) => {
    try {
      setLoading(true);
      const response = await api.post(`/api/training-files/${fileId}`, {
        content,
      });
      if (response.data.success) {
        toast.success(`${response.data.message || "File updated successfully!"}`);
      }
      return response.data;
    } catch (error) {
      console.error(`Error updating training file ${fileId}:`, error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot update file");
        return { success: false, error: "Backend offline" };
      }
      toast.error("Failed to update file");
      return { success: false, error: errorMessage(error) };
    } finally {
      setLoading(false);
    }
  }, []);

  const getTrainingFileBackups = useCallback(async (/** @type {string} */ fileId) => {
    try {
      const response = await api.get(`/api/training-files/${fileId}/backups`);
      return response.data;
    } catch (error) {
      console.error(`Error getting backups for ${fileId}:`, error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", backups: [] };
      }
      return { success: false, error: errorMessage(error) };
    }
  }, []);

  const restoreTrainingFileBackup = useCallback(async (/** @type {string} */ fileId, /** @type {string} */ filename) => {
    try {
      setLoading(true);
      const response = await api.post(`/api/training-files/${fileId}/restore`, {
        filename,
      });
      if (response.data.success) {
        toast.success("File restored from backup!");
      }
      return response.data;
    } catch (error) {
      console.error(`Error restoring backup for ${fileId}:`, error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot restore backup");
        return { success: false, error: "Backend offline" };
      }
      toast.error("Failed to restore backup");
      return { success: false, error: errorMessage(error) };
    } finally {
      setLoading(false);
    }
  }, []);

  const getTrainingFileStats = useCallback(async (/** @type {string} */ fileId) => {
    try {
      const response = await api.get(`/api/training-files/${fileId}/stats`);
      return response.data;
    } catch (error) {
      console.error(`Error getting stats for ${fileId}:`, error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return {
          success: false,
          error: "Backend offline",
          stats: { lines: 0, words: 0, characters: 0, file_size: 0 },
        };
      }
      return { success: false, error: errorMessage(error) };
    }
  }, []);

  // ✨ NEW: Bot Instructions Management functions
  const getInstructions = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get("/api/instructions/get");
      return response.data;
    } catch (error) {
      console.error("Error getting instructions:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot load instructions");
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: errorMessage(error) };
    } finally {
      setLoading(false);
    }
  }, []);

  const updateInstructions = useCallback(async (/** @type {string} */ instructions) => {
    try {
      setLoading(true);
      const response = await api.post("/api/instructions/update", {
        instructions,
      });
      if (response.data.success) {
        toast.success(
          "✅ Instructions updated! Bot will use new guidelines immediately."
        );
      }
      return response.data;
    } catch (error) {
      console.error("Error updating instructions:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot update instructions");
        return { success: false, error: "Backend offline" };
      }
      toast.error("Failed to update instructions");
      return { success: false, error: errorMessage(error) };
    } finally {
      setLoading(false);
    }
  }, []);

  const getInstructionsBackups = useCallback(async () => {
    try {
      const response = await api.get("/api/instructions/backups");
      return response.data;
    } catch (error) {
      console.error("Error getting backups:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", backups: [] };
      }
      return { success: false, error: errorMessage(error) };
    }
  }, []);

  const restoreInstructionsBackup = useCallback(async (/** @type {string} */ filename) => {
    try {
      setLoading(true);
      const response = await api.post("/api/instructions/restore", {
        filename,
      });
      if (response.data.success) {
        toast.success("✅ Instructions restored from backup!");
      }
      return response.data;
    } catch (error) {
      console.error("Error restoring backup:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        toast.error("Backend offline - cannot restore backup");
        return { success: false, error: "Backend offline" };
      }
      toast.error("Failed to restore backup");
      return { success: false, error: errorMessage(error) };
    } finally {
      setLoading(false);
    }
  }, []);

  const getInstructionsStats = useCallback(async () => {
    try {
      const response = await api.get("/api/instructions/stats");
      return response.data;
    } catch (error) {
      console.error("Error getting instructions stats:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return {
          success: false,
          error: "Backend offline",
          stats: {
            lines: 0,
            words: 0,
            characters: 0,
            sections: 0,
          },
        };
      }
      return { success: false, error: errorMessage(error) };
    }
  }, []);

  // Activity Flow API (User ↔ Bot ↔ AI transparency)
  const getFlowLogs = useCallback(async (limit = 50, search = "") => {
    try {
      const params = new URLSearchParams({ limit: String(limit) });
      if (search && search.trim()) params.set("search", search.trim());
      const response = await api.get(`/api/flow/logs?${params.toString()}`, {
        timeout: 12000,
      });
      return response.data;
    } catch (error) {
      console.error("Error getting flow logs:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", data: [], count: 0 };
      }
      return { success: false, error: errorMessage(error), data: [], count: 0 };
    }
  }, []);

  // Content Files API (Knowledge, Price, Style managers - dynamic retrieval)
  const getContentFilesList = useCallback(async (/** @type {string} */ section) => {
    try {
      const response = await api.get(`/api/content-files/${section}/list`);
      return response.data;
    } catch (error) {
      console.error("Error getting content files list:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", data: [], count: 0 };
      }
      return { success: false, error: errorMessage(error), data: [], count: 0 };
    }
  }, []);

  const getContentFile = useCallback(async (/** @type {string} */ section, /** @type {string} */ fileId) => {
    try {
      const response = await api.get(`/api/content-files/${section}/${fileId}`);
      return response.data;
    } catch (error) {
      console.error("Error getting content file:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: errorMessage(error) };
    }
  }, []);

  const createContentFile = useCallback(async (/** @type {string} */ section, /** @type {Record<string, unknown>} */ payload) => {
    try {
      const response = await api.post(`/api/content-files/${section}/create`, payload);
      return response.data;
    } catch (error) {
      console.error("Error creating content file:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  const updateContentFile = useCallback(async (/** @type {string} */ section, /** @type {string} */ fileId, /** @type {Record<string, unknown>} */ payload) => {
    try {
      const response = await api.put(`/api/content-files/${section}/${fileId}`, payload);
      return response.data;
    } catch (error) {
      console.error("Error updating content file:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  const deleteContentFile = useCallback(async (/** @type {string} */ section, /** @type {string} */ fileId) => {
    try {
      const response = await api.delete(`/api/content-files/${section}/${fileId}`);
      return response.data;
    } catch (error) {
      console.error("Error deleting content file:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  const getDynamicMessages = useCallback(async () => {
    try {
      const response = await api.get("/api/content-files/dynamic-messages");
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", data: {} };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error), data: {} };
    }
  }, []);

  const updateDynamicMessages = useCallback(async (/** @type {Record<string, unknown>} */ data) => {
    try {
      const response = await api.put("/api/content-files/dynamic-messages", { data });
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  return {
    loading,
    currentProvider,
    botStatus,
    fetchBotStatus,
    testTextMessage,
    testVoiceTranscription,
    testImageAnalysis,
    testImageWithUrl,
    testVoiceWithText,
    addTrainingData,
    getTrainingData,
    deleteTrainingData,
    searchTrainingData,
    switchProvider,
    testMessageWithProvider,
    testWebhookSimulation,
    // Live Chat functions
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
    // Q&A Management functions
    getQAPairs,
    createQAPair,
    updateQAPair,
    deleteQAPair,
    testQAMatch,
    getQAStatistics,
    getQACategories,
    rewriteAnswer,
    translateQAPair,
    // Local Q&A Management functions (JSON file-based)
    getLocalQAPairs,
    createLocalQAPair,
    updateLocalQAPair,
    deleteLocalQAPair,
    getLocalQAStatistics,
    // Feedback functions
    submitFeedback,
    getFeedbackStats,
    getWrongAnswers,
    // Bot Instructions Management functions
    getInstructions,
    updateInstructions,
    getInstructionsBackups,
    restoreInstructionsBackup,
    getInstructionsStats,
    // Training Files Management functions
    getTrainingFiles,
    getTrainingFile,
    updateTrainingFile,
    getTrainingFileBackups,
    restoreTrainingFileBackup,
    getTrainingFileStats,
    // Activity Flow (User ↔ Bot ↔ AI)
    getFlowLogs,
    // Content Files (Knowledge, Price, Style managers)
    getContentFilesList,
    getContentFile,
    createContentFile,
    updateContentFile,
    deleteContentFile,
    getDynamicMessages,
    updateDynamicMessages,
  };
};
