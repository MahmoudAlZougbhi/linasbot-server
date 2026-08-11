import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import {
  DocumentTextIcon,
  CheckCircleIcon,
  ClockIcon,
  MagnifyingGlassIcon,
} from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import {
  FILE_ICONS,
  FILE_COLORS,
  FILE_HELP_TEXT,
  formatDate,
  formatFileSize,
  findTrainingSearchMatches,
} from "./TrainingFileEditor.meta";
import { TrainingFileEditorSearch } from "./TrainingFileEditorSearch";
import { TrainingFileEditorBackups } from "./TrainingFileEditorBackups";

/** @param {{ fileId: keyof typeof FILE_ICONS | string; title: string; description?: string }} props */
const TrainingFileEditor = ({ fileId, title, description: _description }) => {
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
  const [stats, setStats] = useState(/** @type {FileStatsRecord | null} */ (null));
  const [backups, setBackups] = useState(/** @type {TrainingBackupRecord[]} */ ([]));
  const [lastModified, setLastModified] = useState(/** @type {string | null} */ (null));
  const [isLoading, setIsLoading] = useState(true);

  const [searchQuery, setSearchQuery] = useState("");
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [currentMatchIndex, setCurrentMatchIndex] = useState(0);
  const textareaRef = useRef(/** @type {HTMLTextAreaElement | null} */ (null));
  const searchInputRef = useRef(/** @type {HTMLInputElement | null} */ (null));

  const fileKey = /** @type {keyof typeof FILE_ICONS} */ (fileId);
  const Icon = FILE_ICONS[fileKey] || DocumentTextIcon;
  const colors = FILE_COLORS[fileKey] || FILE_COLORS.knowledge_base;
  const helpText = FILE_HELP_TEXT[fileKey] || "";

  const loadFile = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await getTrainingFile(fileId);
      if (response.success) {
        setContent(response.content || "");
        setOriginalContent(response.content || "");
        setLastModified(response.last_modified);
      }
    } catch {
      console.error(`Failed to load ${fileId}:`);
    } finally {
      setIsLoading(false);
    }
  }, [fileId, getTrainingFile]);

  const loadStats = useCallback(async () => {
    try {
      const response = await getTrainingFileStats(fileId);
      if (response.success) {
        setStats(response.stats);
      }
    } catch {
      console.error(`Failed to load stats for ${fileId}:`);
    }
  }, [fileId, getTrainingFileStats]);

  const loadBackups = useCallback(async () => {
    try {
      const response = await getTrainingFileBackups(fileId);
      if (response.success) {
        setBackups(response.backups);
      }
    } catch {
      console.error(`Failed to load backups for ${fileId}:`);
    }
  }, [fileId, getTrainingFileBackups]);

  useEffect(() => {
    loadFile();
    loadStats();
    loadBackups();
  }, [loadFile, loadStats, loadBackups]);

  useEffect(() => {
    setHasChanges(content !== originalContent);
  }, [content, originalContent]);

  const searchResults = useMemo(
    () => findTrainingSearchMatches(content, searchQuery),
    [searchQuery, content]
  );

  useEffect(() => {
    setCurrentMatchIndex(0);
  }, [searchQuery]);

  useEffect(() => {
    if (isSearchOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [isSearchOpen]);

  const navigateToMatch = useCallback(
    (/** @type {number} */ matchIndex) => {
      if (searchResults.length === 0 || !textareaRef.current) return;

      const match = searchResults[matchIndex];
      if (!match) return;

      const textarea = textareaRef.current;
      textarea.focus();
      textarea.setSelectionRange(match.index, match.index + searchQuery.length);

      const lineHeight = 20;
      const scrollPosition = (match.lineNumber - 5) * lineHeight;
      textarea.scrollTop = Math.max(0, scrollPosition);

      setCurrentMatchIndex(matchIndex);
    },
    [searchResults, searchQuery]
  );

  const goToNextMatch = useCallback(() => {
    if (searchResults.length === 0) return;
    const nextIndex = (currentMatchIndex + 1) % searchResults.length;
    navigateToMatch(nextIndex);
  }, [searchResults.length, currentMatchIndex, navigateToMatch]);

  const goToPrevMatch = useCallback(() => {
    if (searchResults.length === 0) return;
    const prevIndex = (currentMatchIndex - 1 + searchResults.length) % searchResults.length;
    navigateToMatch(prevIndex);
  }, [searchResults.length, currentMatchIndex, navigateToMatch]);

  const toggleSearch = () => {
    setIsSearchOpen(!isSearchOpen);
    if (isSearchOpen) {
      setSearchQuery("");
    }
  };

  useEffect(() => {
    /** @param {KeyboardEvent} e */
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "f") {
        e.preventDefault();
        setIsSearchOpen(true);
      }
      if (e.key === "Escape" && isSearchOpen) {
        setIsSearchOpen(false);
        setSearchQuery("");
      }
      if (e.key === "Enter" && isSearchOpen && searchResults.length > 0) {
        e.preventDefault();
        if (e.shiftKey) {
          goToPrevMatch();
        } else {
          goToNextMatch();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isSearchOpen, searchResults.length, goToNextMatch, goToPrevMatch]);

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

  /** @param {string} filename */
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
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="card">
            <div className="flex items-center space-x-3">
              <div className={`p-2 rounded-lg ${colors.bg}`}>
                <DocumentTextIcon className={`w-5 h-5 ${colors.icon}`} />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-600">Lines</p>
                <p className={`text-xl font-bold ${colors.icon}`}>{stats.lines}</p>
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
                <p className="text-xl font-bold text-purple-600">{stats.characters}</p>
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
            <button
              onClick={toggleSearch}
              className={`p-2 rounded-lg transition-all duration-200 ${
                isSearchOpen
                  ? `${colors.bg} ${colors.icon}`
                  : "text-slate-400 hover:text-slate-600 hover:bg-slate-100"
              }`}
              title="Search (Ctrl+F)"
            >
              <MagnifyingGlassIcon className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="space-y-4">
          <TrainingFileEditorSearch
            isSearchOpen={isSearchOpen}
            colors={colors}
            searchInputRef={searchInputRef}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            searchResults={searchResults}
            currentMatchIndex={currentMatchIndex}
            goToPrevMatch={goToPrevMatch}
            goToNextMatch={goToNextMatch}
            toggleSearch={toggleSearch}
            navigateToMatch={navigateToMatch}
          />

          {helpText && (
            <div className={`${colors.helpBg} border ${colors.helpBorder} rounded-lg p-4`}>
              <p className={`text-sm ${colors.helpText}`}>
                <strong>How it works:</strong> {helpText}
              </p>
            </div>
          )}

          <textarea
            ref={textareaRef}
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
                <button onClick={handleDiscard} className="btn-ghost" disabled={loading}>
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

      <TrainingFileEditorBackups
        backups={backups}
        loading={loading}
        handleRestore={handleRestore}
      />
    </motion.div>
  );
};

export default TrainingFileEditor;
