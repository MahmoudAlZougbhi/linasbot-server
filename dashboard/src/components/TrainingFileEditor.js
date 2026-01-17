import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  DocumentTextIcon,
  CheckCircleIcon,
  ClockIcon,
  ArrowPathIcon,
  BookOpenIcon,
  CurrencyDollarIcon,
  SparklesIcon,
} from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import toast from "react-hot-toast";

// Icon mapping for different file types
const FILE_ICONS = {
  knowledge_base: BookOpenIcon,
  style_guide: SparklesIcon,
  price_list: CurrencyDollarIcon,
};

// Color configuration for different file types
const FILE_COLORS = {
  knowledge_base: {
    icon: "text-blue-600",
    bg: "bg-blue-100",
    helpBg: "bg-blue-50",
    helpBorder: "border-blue-200",
    helpText: "text-blue-800",
  },
  style_guide: {
    icon: "text-purple-600",
    bg: "bg-purple-100",
    helpBg: "bg-purple-50",
    helpBorder: "border-purple-200",
    helpText: "text-purple-800",
  },
  price_list: {
    icon: "text-green-600",
    bg: "bg-green-100",
    helpBg: "bg-green-50",
    helpBorder: "border-green-200",
    helpText: "text-green-800",
  },
};

// Description/help text for each file type
const FILE_HELP_TEXT = {
  knowledge_base:
    "This knowledge base contains information the bot can reference when answering customer questions. Include product details, procedures, FAQs, and any other relevant information.",
  style_guide:
    "These instructions guide the AI's behavior in every customer conversation. The bot reads these guidelines before responding to ensure consistent, professional interactions.",
  price_list:
    "List your service prices here. The bot will reference this when customers ask about pricing. Format: one service per line with price.",
};

const TrainingFileEditor = ({ fileId, title, description }) => {
  const {
    getTrainingFile,
    updateTrainingFile,
    getTrainingFileBackups,
    restoreTrainingFileBackup,
    getTrainingFileStats,
    loading,
  } = useApi();

  const [content, setContent] = useState("");
  const [originalContent, setOriginalContent] = useState("");
  const [hasChanges, setHasChanges] = useState(false);
  const [stats, setStats] = useState(null);
  const [backups, setBackups] = useState([]);
  const [lastModified, setLastModified] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const Icon = FILE_ICONS[fileId] || DocumentTextIcon;
  const colors = FILE_COLORS[fileId] || FILE_COLORS.knowledge_base;
  const helpText = FILE_HELP_TEXT[fileId] || "";

  useEffect(() => {
    loadFile();
    loadStats();
    loadBackups();
  }, [fileId]);

  useEffect(() => {
    setHasChanges(content !== originalContent);
  }, [content, originalContent]);

  const loadFile = async () => {
    try {
      setIsLoading(true);
      const response = await getTrainingFile(fileId);
      if (response.success) {
        setContent(response.content || "");
        setOriginalContent(response.content || "");
        setLastModified(response.last_modified);
      }
    } catch (error) {
      console.error(`Failed to load ${fileId}:`, error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const response = await getTrainingFileStats(fileId);
      if (response.success) {
        setStats(response.stats);
      }
    } catch (error) {
      console.error(`Failed to load stats for ${fileId}:`, error);
    }
  };

  const loadBackups = async () => {
    try {
      const response = await getTrainingFileBackups(fileId);
      if (response.success) {
        setBackups(response.backups || []);
      }
    } catch (error) {
      console.error(`Failed to load backups for ${fileId}:`, error);
    }
  };

  const handleSave = async () => {
    try {
      const response = await updateTrainingFile(fileId, content);
      if (response.success) {
        setOriginalContent(content);
        setLastModified(response.last_modified);
        await loadStats();
        await loadBackups();
      }
    } catch (error) {
      console.error(`Failed to save ${fileId}:`, error);
    }
  };

  const handleRestore = async (filename) => {
    if (!window.confirm(`Restore ${title} from backup: ${filename}?`)) {
      return;
    }

    try {
      const response = await restoreTrainingFileBackup(fileId, filename);
      if (response.success) {
        await loadFile();
        await loadStats();
        await loadBackups();
      }
    } catch (error) {
      console.error(`Failed to restore backup for ${fileId}:`, error);
    }
  };

  const handleDiscard = () => {
    if (window.confirm("Discard all changes?")) {
      setContent(originalContent);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return "Unknown";
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
  };

  if (isLoading) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-center h-64"
      >
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </motion.div>
    );
  }

  return (
    <motion.div
      key={fileId}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="card">
            <div className="flex items-center space-x-3">
              <div className={`p-2 rounded-lg ${colors.bg}`}>
                <DocumentTextIcon className={`w-5 h-5 ${colors.icon}`} />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-600">Lines</p>
                <p className={`text-xl font-bold ${colors.icon}`}>
                  {stats.lines}
                </p>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="flex items-center space-x-3">
              <div className="p-2 rounded-lg bg-green-100">
                <CheckCircleIcon className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-600">Words</p>
                <p className="text-xl font-bold text-green-600">{stats.words}</p>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="flex items-center space-x-3">
              <div className="p-2 rounded-lg bg-purple-100">
                <DocumentTextIcon className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-600">Characters</p>
                <p className="text-xl font-bold text-purple-600">
                  {stats.characters}
                </p>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="flex items-center space-x-3">
              <div className="p-2 rounded-lg bg-orange-100">
                <ClockIcon className="w-5 h-5 text-orange-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-600">Size</p>
                <p className="text-xl font-bold text-orange-600">
                  {formatFileSize(stats.file_size)}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Editor */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold text-slate-800 font-display flex items-center">
              <Icon className={`w-6 h-6 mr-2 ${colors.icon}`} />
              {title}
            </h2>
            {lastModified && (
              <p className="text-xs text-slate-500 mt-1">
                Last modified: {formatDate(lastModified)}
              </p>
            )}
          </div>

          <div className="flex items-center space-x-2">
            {hasChanges && (
              <span className="text-xs px-2 py-1 rounded-full bg-orange-100 text-orange-700 font-medium">
                Unsaved changes
              </span>
            )}
          </div>
        </div>

        <div className="space-y-4">
          {helpText && (
            <div className={`${colors.helpBg} border ${colors.helpBorder} rounded-lg p-4`}>
              <p className={`text-sm ${colors.helpText}`}>
                <strong>How it works:</strong> {helpText}
              </p>
            </div>
          )}

          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={`Enter ${title.toLowerCase()} content here...`}
            className="input-field w-full h-96 resize-none font-mono text-sm"
            style={{ fontFamily: "monospace" }}
          />

          <div className="flex items-center justify-between">
            <div className="text-sm text-slate-600">
              {content.length} characters • {content.split("\n").length} lines
            </div>

            <div className="flex space-x-3">
              {hasChanges && (
                <button
                  onClick={handleDiscard}
                  className="btn-ghost"
                  disabled={loading}
                >
                  Discard Changes
                </button>
              )}
              <button
                onClick={handleSave}
                disabled={loading || !hasChanges}
                className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <div className="flex items-center">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Saving...
                  </div>
                ) : (
                  <>
                    <CheckCircleIcon className="w-4 h-4 mr-2" />
                    Save {title}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Backups */}
      {backups.length > 0 && (
        <div className="card">
          <h3 className="text-lg font-bold text-slate-800 font-display mb-4 flex items-center">
            <ArrowPathIcon className="w-5 h-5 mr-2 text-slate-600" />
            Backup History ({backups.length})
          </h3>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {backups.map((backup) => (
              <div
                key={backup.filename}
                className="flex items-center justify-between p-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <div className="flex-1">
                  <p className="text-sm font-medium text-slate-800">
                    {backup.filename}
                  </p>
                  <p className="text-xs text-slate-500">
                    {formatDate(backup.created)} • {formatFileSize(backup.size)}
                  </p>
                </div>
                <button
                  onClick={() => handleRestore(backup.filename)}
                  disabled={loading}
                  className="text-sm px-3 py-1 rounded-lg bg-blue-100 text-blue-700 hover:bg-blue-200 transition-colors disabled:opacity-50"
                >
                  Restore
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default TrainingFileEditor;
