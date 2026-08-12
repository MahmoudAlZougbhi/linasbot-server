import { useCallback } from "react";
import toast from "react-hot-toast";
import { errorMessage, getAxiosErrorCode } from "../utils/apiValidate";
import { api } from "./useApiClient";

/** @param {{ setLoading: Function }} args */
export function useApiQA({ setLoading }) {
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

  const getRecentFeedback = useCallback(async (limit = 20) => {
    try {
      const response = await api.get(`/api/feedback/recent?limit=${limit}`);
      return response.data;
    } catch (error) {
      console.error("Error getting recent feedback:", error);
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", feedback: [] };
      }
      return { success: false, error: errorMessage(error) };
    }
  }, []);


  return {
    getQAPairs,
    createQAPair,
    updateQAPair,
    deleteQAPair,
    testQAMatch,
    getQAStatistics,
    getQACategories,
    rewriteAnswer,
    translateQAPair,
    getLocalQAPairs,
    createLocalQAPair,
    updateLocalQAPair,
    deleteLocalQAPair,
    getLocalQAStatistics,
    submitFeedback,
    getFeedbackStats,
    getWrongAnswers,
    getRecentFeedback,
  };
}
