import { useCallback } from "react";
import toast from "react-hot-toast";
import { errorMessage, getAxiosErrorCode } from "../utils/apiValidate";
import { api } from "./useApiClient";

/** @param {{ setLoading: Function }} args */
export function useApiTraining({ setLoading }) {
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

  // Legacy /api/instructions hooks removed — use tenant CM (/api/cm) for style/AI basics.

  return {
    getTrainingFiles,
    getTrainingFile,
    updateTrainingFile,
    getTrainingFileBackups,
    restoreTrainingFileBackup,
    getTrainingFileStats,
  };
}
