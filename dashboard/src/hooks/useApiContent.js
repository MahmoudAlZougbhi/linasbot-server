import { useCallback } from "react";
import toast from "react-hot-toast";
import { errorMessage, getAxiosErrorCode, getAxiosResponseDetail, isAxiosLikeError } from "../utils/apiValidate";
import { api } from "./useApiClient";

export function useApiContent() {
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

  // AI Setup control-plane APIs
  const getCmMeta = useCallback(async () => {
    try {
      const response = await api.get("/api/cm/meta");
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: errorMessage(error) };
    }
  }, []);

  const getCmDraft = useCallback(async (/** @type {string} */ section) => {
    try {
      const response = await api.get(`/api/cm/draft/${section}`);
      const etagHeader = response.headers?.etag || response.headers?.ETag;
      return {
        ...response.data,
        etag: typeof etagHeader === "string" ? etagHeader : response.data?.data?.etag,
      };
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  const uploadCmMedia = useCallback(async (/** @type {File | Blob} */ file) => {
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await api.post("/api/cm/media", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  const putCmDraft = useCallback(
    async (
      /** @type {string} */ section,
      /** @type {Record<string, unknown>} */ payload,
      /** @type {string} */ ifMatch
    ) => {
      try {
        const response = await api.put(`/api/cm/draft/${section}`, payload, {
          headers: { "If-Match": ifMatch },
        });
        const etagHeader = response.headers?.etag || response.headers?.ETag;
        return {
          ...response.data,
          etag: typeof etagHeader === "string" ? etagHeader : response.data?.data?.etag,
        };
      } catch (error) {
        if (isAxiosLikeError(error) && error.response?.status === 409) {
          const data =
            error.response.data && typeof error.response.data === "object"
              ? error.response.data
              : {};
          return {
            success: false,
            conflict: true,
            ...data,
            error: data.message || data.error || "Draft conflict",
          };
        }
        if (getAxiosErrorCode(error) === "ERR_NETWORK") {
          return { success: false, error: "Backend offline" };
        }
        return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
      }
    },
    []
  );

  const validateCmDraft = useCallback(async (/** @type {Record<string, unknown>} */ payload = {}) => {
    try {
      const response = await api.post("/api/cm/validate", payload);
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", ok: false, errors: [], warnings: [] };
      }
      return {
        success: false,
        error: getAxiosResponseDetail(error) || errorMessage(error),
        ok: false,
        errors: [],
        warnings: [],
      };
    }
  }, []);

  const quoteCmPricing = useCallback(async (/** @type {Record<string, unknown>} */ body = {}) => {
    try {
      const response = await api.post("/api/cm/pricing/quote", body);
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      if (isAxiosLikeError(error) && error.response?.data && typeof error.response.data === "object") {
        return {
          success: false,
          ...error.response.data,
          error: error.response.data.message || error.response.data.error || errorMessage(error),
        };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  const getCmSourcesInventory = useCallback(async () => {
    try {
      const response = await api.get("/api/cm/sources/inventory");
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  const listCmFaq = useCallback(async (/** @type {Record<string, unknown>} */ params = {}) => {
    try {
      const response = await api.get("/api/cm/faq", { params });
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", data: [] };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error), data: [] };
    }
  }, []);

  const createCmFaq = useCallback(async (/** @type {Record<string, unknown>} */ body) => {
    try {
      const response = await api.post("/api/cm/faq", body);
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  const archiveCmFaq = useCallback(async (/** @type {string} */ qaGroupId) => {
    try {
      const response = await api.post(`/api/cm/faq/${qaGroupId}/archive`);
      return response.data;
    } catch (error) {
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  const patchCmFaqVariant = useCallback(
    async (
      /** @type {string} */ qaGroupId,
      /** @type {string} */ language,
      /** @type {Record<string, unknown>} */ body
    ) => {
      try {
        const response = await api.patch(`/api/cm/faq/${qaGroupId}/variants/${language}`, body);
        return response.data;
      } catch (error) {
        return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
      }
    },
    []
  );

  const regenerateCmFaq = useCallback(
    async (/** @type {string} */ qaGroupId, /** @type {Record<string, unknown>} */ body = {}) => {
      try {
        const response = await api.post(`/api/cm/faq/${qaGroupId}/regenerate`, body);
        return response.data;
      } catch (error) {
        return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
      }
    },
    []
  );

  const publishCm = useCallback(async () => {
    try {
      const response = await api.post("/api/cm/publish", {});
      return response.data;
    } catch (error) {
      if (isAxiosLikeError(error) && error.response?.status === 403) {
        const data =
          error.response.data && typeof error.response.data === "object"
            ? error.response.data
            : {};
        return {
          success: false,
          error: data.message || data.detail || data.error || "Publish disabled",
          message: data.message || data.detail,
        };
      }
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  const getCmVersions = useCallback(async () => {
    try {
      const response = await api.get("/api/cm/versions");
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline", data: [], count: 0 };
      }
      return { success: false, error: errorMessage(error), data: [], count: 0 };
    }
  }, []);

  const rollbackCmVersion = useCallback(async (/** @type {string} */ versionId) => {
    try {
      const response = await api.post(`/api/cm/versions/${versionId}/rollback`, {});
      return response.data;
    } catch (error) {
      if (isAxiosLikeError(error) && error.response?.status === 403) {
        const data =
          error.response.data && typeof error.response.data === "object"
            ? error.response.data
            : {};
        return {
          success: false,
          error: data.message || data.detail || data.error || "Publish disabled",
        };
      }
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  const buildCmPreviewPacket = useCallback(async (/** @type {Record<string, unknown>} */ payload = {}) => {
    try {
      const response = await api.post("/api/cm/preview-packet", payload);
      return response.data;
    } catch (error) {
      if (getAxiosErrorCode(error) === "ERR_NETWORK") {
        return { success: false, error: "Backend offline" };
      }
      return { success: false, error: getAxiosResponseDetail(error) || errorMessage(error) };
    }
  }, []);

  return {
    getFlowLogs,
    getContentFilesList,
    getContentFile,
    createContentFile,
    updateContentFile,
    deleteContentFile,
    getDynamicMessages,
    updateDynamicMessages,
    getCmMeta,
    getCmDraft,
    uploadCmMedia,
    putCmDraft,
    validateCmDraft,
    quoteCmPricing,
    getCmSourcesInventory,
    listCmFaq,
    createCmFaq,
    archiveCmFaq,
    patchCmFaqVariant,
    regenerateCmFaq,
    publishCm,
    getCmVersions,
    rollbackCmVersion,
    buildCmPreviewPacket,
  };
}
