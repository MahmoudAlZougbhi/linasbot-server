import { useCallback } from "react";
import toast from "react-hot-toast";
import { getAxiosErrorCode } from "../utils/apiValidate";
import { api } from "./useApiClient";

/** @param {{ setLoading: Function; currentProvider: string; setCurrentProvider: Function; setBotStatus: Function }} args */
export function useApiTesting({ setLoading, currentProvider, setCurrentProvider, setBotStatus }) {
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
  }, [setLoading, setBotStatus]);

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
        if (code === "ERR_NETWORK") {
          toast.error("Backend offline — cannot run test");
          return { success: false, error: "Backend offline" };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    }, [setLoading]);

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
    }, [currentProvider, setLoading]);

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
        if (code === "ERR_NETWORK") {
          toast.error("Backend offline — cannot run test");
          return { success: false, error: "Backend offline" };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    }, [currentProvider, setLoading]);

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
        if (code === "ERR_NETWORK") {
          toast.error("Backend offline — cannot run test");
          return { success: false, error: "Backend offline" };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    }, [currentProvider, setLoading]);

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
        if (code === "ERR_NETWORK") {
          toast.error("Backend offline — cannot run test");
          return { success: false, error: "Backend offline" };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    }, [currentProvider, setLoading]);

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
    }, [setLoading]);

  const getTrainingData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get("/api/training/list");
      return response.data;
    } finally {
      setLoading(false);
    }
  }, [setLoading]);

  const deleteTrainingData = useCallback(async (/** @type {string} */ id) => {
    try {
      setLoading(true);
      const response = await api.delete(`/api/training/${id}`);
      toast.success("Training data deleted successfully!");
      return response.data;
    } finally {
      setLoading(false);
    }
  }, [setLoading]);

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
  }, [setLoading]);

  // Provider switching
  const switchProvider = useCallback(async (/** @type {string} */ provider) => {
    try {
      setLoading(true);
      const response = await api.post("/api/switch-provider", {
        provider,
      });

      setCurrentProvider(provider);
      setBotStatus((/** @type {BotStatus | Record<string, unknown>} */ prev) => ({
        ...prev,
        currentProvider: provider,
      }));

      toast.success(`Switched to ${provider}`);
      return response.data;
    } catch (error) {
      const code = getAxiosErrorCode(error);
      if (code === "ERR_NETWORK") {
        toast.error("Backend offline — cannot switch provider");
        return { success: false, error: "Backend offline" };
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, [setLoading, setBotStatus, setCurrentProvider]);

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
    }, [currentProvider, setLoading]);

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
        if (code === "ERR_NETWORK") {
          toast.error("Backend offline — cannot run test");
          return { success: false, error: "Backend offline" };
        }
        throw error;
      } finally {
        setLoading(false);
      }
    }, [currentProvider, setLoading]);


  return {
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
  };
}
