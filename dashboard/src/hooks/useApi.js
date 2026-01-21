import { useState, useCallback } from "react";
import axios from "axios";
import toast from "react-hot-toast";

// Create axios instance with default config
const api = axios.create({
  baseURL:
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1"
      ? "http://localhost:8003" // Local development
      : "", // Production - use same origin (works on any domain)
  timeout: 90000, // 90 seconds - increased for slow GPT responses
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor
api.interceptors.request.use(
  (config) => {
    // Add loading state or auth tokens here if needed
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
    // Handle network errors gracefully (silent)
    if (error.code === "ERR_NETWORK") {
      // Silent - no console logs for network errors
      if (process.env.NODE_ENV === "development") {
        return Promise.reject(error);
      }
    }

    // Handle timeout errors gracefully (silent)
    if (error.code === "ECONNABORTED") {
      // Silent - no console logs for timeout errors
      // These are expected for slow Firestore queries
      return Promise.reject(error);
    }

    const message =
      error.response?.data?.message || error.message || "An error occurred";

    // Only show toast for non-network and non-timeout errors
    if (error.code !== "ERR_NETWORK" && error.code !== "ECONNABORTED") {
      toast.error(message);
    }

    return Promise.reject(error);
  }
);

export const useApi = () => {
  const [loading, setLoading] = useState(false);
  const [currentProvider, setCurrentProvider] = useState("meta");
  const [botStatus, setBotStatus] = useState({
    status: "unknown",
    uptime: 0,
    responseTime: 0,
    features: [],
    currentProvider: "meta",
  });

  // Fetch bot status
  const fetchBotStatus = useCallback(async () => {
    try {
      setLoading(true);
      // Use shorter timeout for initial status check
      const response = await api.get("/api/test", {
        timeout: 10000, // 10 seconds - just for health check
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
      // Set offline status but don't throw error for network/timeout issues
      setBotStatus({
        status: error.code === "ECONNABORTED" ? "slow" : "offline",
        uptime: 0,
        responseTime: 0,
        features: [],
      });

      // Only throw non-network and non-timeout errors
      if (error.code !== "ERR_NETWORK" && error.code !== "ECONNABORTED") {
        throw error;
      }

      // Return mock data for network/timeout errors
      return {
        status: error.code === "ECONNABORTED" ? "slow" : "offline",
        message: error.code === "ECONNABORTED"
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
        // Handle network error with mock response
        if (error.code === "ERR_NETWORK") {
          toast.info("Backend offline - showing mock response");
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
    async (audioFile, provider, userPhone) => {
      try {
        setLoading(true);
        const formData = new FormData();
        formData.append("audio", audioFile);
        formData.append("phone", userPhone || "123456789");
        formData.append("provider", provider || currentProvider);
        formData.append("timestamp", Date.now());

        const response = await api.post("/api/test-voice", formData, {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        });

        toast.success("Voice message processed!");
        return response.data;
      } catch (error) {
        throw error;
      } finally {
        setLoading(false);
      }
    },
    [currentProvider]
  );

  // Test image analysis (file upload)
  const testImageAnalysis = useCallback(
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
        // Handle network error with mock response
        if (error.code === "ERR_NETWORK") {
          toast.info("Backend offline - showing mock response");
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
        // Handle network error with mock response
        if (error.code === "ERR_NETWORK") {
          toast.info("Backend offline - showing mock response");
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
        // Handle network error with mock response
        if (error.code === "ERR_NETWORK") {
          toast.info("Backend offline - showing mock response");
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
      } catch (error) {
        throw error;
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
    } catch (error) {
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteTrainingData = useCallback(async (id) => {
    try {
      setLoading(true);
      const response = await api.delete(`/api/training/${id}`);
      toast.success("Training data deleted successfully!");
      return response.data;
    } catch (error) {
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  // Search training data
  const searchTrainingData = useCallback(async (query) => {
    try {
      setLoading(true);
      const response = await api.post("/api/training/search", {
        query,
        timestamp: Date.now(),
      });
      return response.data;
    } catch (error) {
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  // Provider switching
  const switchProvider = useCallback(async (provider) => {
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
      // Handle network error gracefully
      if (error.code === "ERR_NETWORK") {
        setCurrentProvider(provider);
        setBotStatus((prev) => ({
          ...prev,
          currentProvider: provider,
        }));
        toast.info(`Switched to ${provider} (offline mode)`);
        return { success: true, provider };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  // Test message with provider
  const testMessageWithProvider = useCallback(
    async (message, provider = currentProvider, userPhone = "") => {
      try {
        setLoading(true);
        const response = await api.post("/api/test-message", {
          phone: userPhone || "123456789",
          message,
          provider,
        });
        toast.success("Message processed successfully!");
        return response.data;
      } catch (error) {
        // Handle network error with mock response
        if (error.code === "ERR_NETWORK") {
          toast.info("Backend offline - showing mock response");
          return {
            success: true,
            bot_response: `Mock response from ${provider}: ${message}`,
            response_time_ms: 100,
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
        // Handle network error with mock response
        if (error.code === "ERR_NETWORK") {
          toast.info("Backend offline - showing mock response");
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

  // Live Chat API functions
  const getLiveConversations = useCallback(async () => {
    try {
      // Increase timeout for live conversations (can be slow with large datasets)
      const response = await api.get("/api/live-chat/active-conversations", {
        timeout: 60000, // 60 seconds
      });
      return response.data;
    } catch (error) {
      // Silent fallback for network/timeout errors (expected for slow queries)
      if (error.code === "ERR_NETWORK" || error.code === "ECONNABORTED") {
        return { success: false, conversations: [], error: error.code === "ECONNABORTED" ? "Request timeout" : "Backend offline" };
      }
      throw error;
    }
  }, []);

  const getWaitingQueue = useCallback(async () => {
    try {
      const response = await api.get("/api/live-chat/waiting-queue");
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
        return { success: false, queue: [], error: "Backend offline" };
      }
      throw error;
    }
  }, []);

  const takeoverConversation = useCallback(
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
        if (error.code === "ERR_NETWORK") {
          toast.error("Backend offline - cannot take over conversation");
          return { success: false, error: "Backend offline" };
        }
        if (error.code === "ECONNABORTED") {
          toast.error("Takeover timed out - please try again");
          return { success: false, error: "timeout of 60000ms exceeded" };
        }
        // Show actual error message from server
        const errorMsg = error.response?.data?.detail || error.response?.data?.error || error.message || "Unknown error";
        toast.error(`Takeover failed: ${errorMsg}`);
        return { success: false, error: errorMsg };
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const releaseConversation = useCallback(async (conversationId, userId) => {
    try {
      setLoading(true);
      const response = await api.post("/api/live-chat/release", {
        conversation_id: conversationId,
        user_id: userId,
      }, {
        timeout: 60000, // 60 seconds - Firestore operations can be slow
      });
      toast.success("Conversation released to bot!");
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot release conversation");
        return { success: false, error: "Backend offline" };
      }
      if (error.code === "ECONNABORTED") {
        toast.error("Release timed out - please try again");
        return { success: false, error: "timeout" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const sendOperatorMessage = useCallback(
    async (
      conversationId,
      userId,
      message,
      operatorId,
      messageType = "text"
    ) => {
      try {
        setLoading(true);
        const response = await api.post("/api/live-chat/send-message", {
          conversation_id: conversationId,
          user_id: userId,
          message,
          operator_id: operatorId,
          message_type: messageType,
        }, {
          timeout: 60000, // 60 seconds - Firestore + WhatsApp operations can be slow
        });
        toast.success("Message sent!");
        return response.data;
      } catch (error) {
        if (error.code === "ERR_NETWORK") {
          toast.error("Backend offline - cannot send message");
          return { success: false, error: "Backend offline" };
        }
        if (error.code === "ECONNABORTED") {
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

  const updateOperatorStatus = useCallback(async (operatorId, status) => {
    try {
      const response = await api.post("/api/live-chat/operator-status", {
        operator_id: operatorId,
        status,
      });
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
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
      if (error.code === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      throw error;
    }
  }, []);

  // ✨ NEW: Q&A Management Functions
  const getQAPairs = useCallback(async (filters = {}) => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filters.category) params.append("category", filters.category);
      if (filters.language) params.append("language", filters.language);
      if (filters.query) params.append("query", filters.query);
      if (filters.active_only !== undefined)
        params.append("active_only", filters.active_only);

      const response = await api.get(`/api/qa/list?${params}`);
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
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

  const createQAPair = useCallback(async (qaData) => {
    try {
      setLoading(true);
      const response = await api.post("/api/qa/create", qaData);
      toast.success("Q&A pair created successfully!");
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot create Q&A pair");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const updateQAPair = useCallback(async (qaId, updates) => {
    try {
      setLoading(true);
      const response = await api.put(`/api/qa/${qaId}`, updates);
      toast.success("Q&A pair updated successfully!");
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot update Q&A pair");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteQAPair = useCallback(async (qaId) => {
    try {
      setLoading(true);
      const response = await api.delete(`/api/qa/${qaId}`);
      toast.success("Q&A pair deleted successfully!");
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot delete Q&A pair");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const testQAMatch = useCallback(async (question, language = "ar") => {
    try {
      setLoading(true);
      const response = await api.post("/api/qa/test-match", {
        question,
        language,
      });
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
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
      if (error.code === "ERR_NETWORK") {
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
      if (error.code === "ERR_NETWORK") {
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
        if (error.code === "ERR_NETWORK") {
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
        if (error.code === "ERR_NETWORK") {
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
  const getLocalQAPairs = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get("/api/local-qa/list");
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
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

  const createLocalQAPair = useCallback(async (qaData) => {
    try {
      setLoading(true);
      const response = await api.post("/api/local-qa/create", qaData);
      if (response.data.success) {
        toast.success("Q&A pair saved to local file!");
      }
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot save Q&A pair");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const updateLocalQAPair = useCallback(async (qaId, updates) => {
    try {
      setLoading(true);
      const response = await api.put(`/api/local-qa/${qaId}`, updates);
      if (response.data.success) {
        toast.success("Q&A pair updated!");
      }
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot update Q&A pair");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteLocalQAPair = useCallback(async (qaId) => {
    try {
      setLoading(true);
      const response = await api.delete(`/api/local-qa/${qaId}`);
      if (response.data.success) {
        toast.success("Q&A pair deleted!");
      }
      return response.data;
    } catch (error) {
      if (error.code === "ERR_NETWORK") {
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
      if (error.code === "ERR_NETWORK") {
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
  const submitFeedback = useCallback(async (feedbackData) => {
    try {
      setLoading(true);
      const response = await api.post("/api/feedback/submit", feedbackData);

      if (response.data.success) {
        toast.success("Feedback submitted successfully!");
        if (response.data.training_result?.success) {
          toast.success("🎓 Bot trained with correct answer!");
        }
      }

      return response.data;
    } catch (error) {
      console.error("Error submitting feedback:", error);
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot submit feedback");
        return { success: false, error: "Backend offline" };
      }
      toast.error("Failed to submit feedback");
      return { success: false, error: error.message };
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
      if (error.code === "ERR_NETWORK") {
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
      return { success: false, error: error.message };
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
      if (error.code === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", wrong_answers: [] };
      }
      return { success: false, error: error.message };
    }
  }, []);

  // ✨ NEW: Training Files Management functions (Knowledge Base, Style Guide, Price List)
  const getTrainingFiles = useCallback(async () => {
    try {
      const response = await api.get("/api/training-files/list");
      return response.data;
    } catch (error) {
      console.error("Error getting training files:", error);
      if (error.code === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", files: [] };
      }
      return { success: false, error: error.message };
    }
  }, []);

  const getTrainingFile = useCallback(async (fileId) => {
    try {
      setLoading(true);
      const response = await api.get(`/api/training-files/${fileId}`);
      return response.data;
    } catch (error) {
      console.error(`Error getting training file ${fileId}:`, error);
      if (error.code === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: error.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const updateTrainingFile = useCallback(async (fileId, content) => {
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
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot update file");
        return { success: false, error: "Backend offline" };
      }
      toast.error("Failed to update file");
      return { success: false, error: error.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const getTrainingFileBackups = useCallback(async (fileId) => {
    try {
      const response = await api.get(`/api/training-files/${fileId}/backups`);
      return response.data;
    } catch (error) {
      console.error(`Error getting backups for ${fileId}:`, error);
      if (error.code === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", backups: [] };
      }
      return { success: false, error: error.message };
    }
  }, []);

  const restoreTrainingFileBackup = useCallback(async (fileId, filename) => {
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
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot restore backup");
        return { success: false, error: "Backend offline" };
      }
      toast.error("Failed to restore backup");
      return { success: false, error: error.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const getTrainingFileStats = useCallback(async (fileId) => {
    try {
      const response = await api.get(`/api/training-files/${fileId}/stats`);
      return response.data;
    } catch (error) {
      console.error(`Error getting stats for ${fileId}:`, error);
      if (error.code === "ERR_NETWORK") {
        return {
          success: false,
          error: "Backend offline",
          stats: { lines: 0, words: 0, characters: 0, file_size: 0 },
        };
      }
      return { success: false, error: error.message };
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
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot load instructions");
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: error.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const updateInstructions = useCallback(async (instructions) => {
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
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot update instructions");
        return { success: false, error: "Backend offline" };
      }
      toast.error("Failed to update instructions");
      return { success: false, error: error.message };
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
      if (error.code === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", backups: [] };
      }
      return { success: false, error: error.message };
    }
  }, []);

  const restoreInstructionsBackup = useCallback(async (filename) => {
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
      if (error.code === "ERR_NETWORK") {
        toast.error("Backend offline - cannot restore backup");
        return { success: false, error: "Backend offline" };
      }
      toast.error("Failed to restore backup");
      return { success: false, error: error.message };
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
      if (error.code === "ERR_NETWORK") {
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
      return { success: false, error: error.message };
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
    getLiveConversations,
    getWaitingQueue,
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
  };
};
