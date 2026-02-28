import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AcademicCapIcon,
  PlusIcon,
  MagnifyingGlassIcon,
  TrashIcon,
  PencilIcon,
  BookOpenIcon,
  CheckCircleIcon,
  XCircleIcon,
  SparklesIcon,
  ClockIcon,
  ArrowPathIcon,
  CurrencyDollarIcon,
  BugAntIcon,
} from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import toast from "react-hot-toast";

import TrainingFileEditor from "../components/TrainingFileEditor";
import ContentFilesPanel from "../components/ContentFilesPanel";

const Training = () => {
  const {
    getLocalQAPairs,
    createLocalQAPairStructured,
    updateLocalQAPair,
    deleteLocalQAPair,
    getLocalQAStatistics,
    getTrainingFiles,
    getTrainingFile,
    updateTrainingFile,
    getTrainingFileBackups,
    restoreTrainingFileBackup,
    getTrainingFileStats,
    getRetrievalDebugLogs,
    loading,
  } = useApi();

  const [activeTab, setActiveTab] = useState("add");
  const [trainingEntries, setTrainingEntries] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [filteredEntries, setFilteredEntries] = useState([]);
  const [manageViewLang, setManageViewLang] = useState("all"); // all | ar | en | fr - which language section to show
  const [statistics, setStatistics] = useState({
    total: 0,
    by_language: {},
    by_category: {},
  });

  // Add training form - Franco only, auto-translates to AR/EN/FR
  const [newQuestion, setNewQuestion] = useState("");
  const [newAnswer, setNewAnswer] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("general");
  const [selectedLanguage, setSelectedLanguage] = useState("ar"); // for edit/delete compatibility

  // Edit mode state
  const [editingEntry, setEditingEntry] = useState(null);
  const [editQuestion, setEditQuestion] = useState("");
  const [editAnswer, setEditAnswer] = useState("");
  const [editCategory, setEditCategory] = useState("general");

  // Delete confirmation modal state
  const [deleteConfirmEntry, setDeleteConfirmEntry] = useState(null);

  // Retrieval debug logs
  const [retrievalLogs, setRetrievalLogs] = useState([]);
  const [retrievalLogsLoading, setRetrievalLogsLoading] = useState(false);

  const tabs = [
    {
      id: "add",
      name: "Add Training",
      icon: PlusIcon,
      color: "from-green-500 to-emerald-500",
    },
    {
      id: "manage",
      name: "Manage Data",
      icon: BookOpenIcon,
      color: "from-blue-500 to-cyan-500",
    },
    {
      id: "knowledge_base",
      name: "Knowledge Base",
      icon: BookOpenIcon,
      color: "from-blue-500 to-indigo-500",
    },
    {
      id: "style_guide",
      name: "Style Guide",
      icon: SparklesIcon,
      color: "from-violet-500 to-purple-500",
    },
    {
      id: "price_list",
      name: "Price List",
      icon: CurrencyDollarIcon,
      color: "from-emerald-500 to-green-500",
    },
    {
      id: "retrieval_debug",
      name: "Retrieval Debug",
      icon: BugAntIcon,
      color: "from-amber-500 to-orange-500",
    },
  ];

  const categories = [
    { value: "general", label: "General", emoji: "💬" },
    { value: "pricing", label: "Pricing", emoji: "💰" },
    { value: "services", label: "Services", emoji: "✨" },
    { value: "appointments", label: "Appointments", emoji: "📅" },
    { value: "medical", label: "Medical", emoji: "🏥" },
    { value: "hours", label: "Working Hours", emoji: "⏰" },
  ];

  useEffect(() => {
    loadStatistics();
  }, []);

  useEffect(() => {
    loadTrainingData();
  }, []);

  const loadRetrievalLogs = async () => {
    setRetrievalLogsLoading(true);
    try {
      const res = await getRetrievalDebugLogs(50);
      setRetrievalLogs(res.data || []);
    } catch (e) {
      setRetrievalLogs([]);
    } finally {
      setRetrievalLogsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "retrieval_debug") {
      loadRetrievalLogs();
      const interval = setInterval(loadRetrievalLogs, 10000); // refresh every 10s
      return () => clearInterval(interval);
    }
  }, [activeTab]);

  useEffect(() => {
    let base = trainingEntries;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      base = trainingEntries.filter((entry) => {
        const texts = [
          entry.question,
          entry.answer,
          entry.question_ar,
          entry.answer_ar,
          entry.question_en,
          entry.answer_en,
          entry.question_fr,
          entry.answer_fr,
        ].filter(Boolean);
        return texts.some((t) => t.toLowerCase().includes(q));
      });
    }
    setFilteredEntries(base);
  }, [searchQuery, trainingEntries]);

  const loadTrainingData = async (language = selectedLanguage) => {
    try {
      const response = await getLocalQAPairs({});
      if (response.success && response.data) {
        setTrainingEntries(response.data);
      } else {
        setTrainingEntries([]);
      }
    } catch (error) {
      console.error("❌ Failed to load Q&A data:", error);
      toast.error("Failed to load training data");
      setTrainingEntries([]);
    }
  };

  const loadStatistics = async () => {
    try {
      const response = await getLocalQAStatistics();
      if (response.success && response.statistics) {
        setStatistics(response.statistics);
      }
    } catch (error) {
      console.error("Failed to load statistics:", error);
    }
  };

  const handleAddTraining = async () => {
    if (!newQuestion.trim() || !newAnswer.trim()) {
      toast.error("Please fill in both question and answer (Franco)");
      return;
    }

    try {
      const qaData = {
        question: newQuestion.trim(),
        answer: newAnswer.trim(),
        category: selectedCategory,
        auto_translate: true, // Always: Franco → AR, EN, FR
      };

      const response = await createLocalQAPairStructured(qaData);

      if (response.success) {
        await loadTrainingData();
        await loadStatistics();
        setNewQuestion("");
        setNewAnswer("");
        setSelectedCategory("general");
        toast.success("✅ Saved! Auto-translated to العربية, English & Français");
      } else {
        toast.error(response.error || "Failed to create Q&A pair");
      }
    } catch (error) {
      console.error("Failed to add Q&A pair:", error);
      toast.error("Failed to create Q&A pair");
    }
  };

  const handleDeleteEntry = async () => {
    if (!deleteConfirmEntry) return;

    try {
      console.log("🗑️ Deleting Q&A pair with ID:", deleteConfirmEntry.id);
      const response = await deleteLocalQAPair(deleteConfirmEntry.id);
      console.log("🗑️ Delete response:", response);

      if (response.success) {
        // Reload from backend
        await loadTrainingData(selectedLanguage);
        await loadStatistics();
        toast.success("✅ Q&A pair deleted successfully!");
        setDeleteConfirmEntry(null);
      } else {
        toast.error(response.error || "Failed to delete Q&A pair");
      }
    } catch (error) {
      console.error("❌ Failed to delete Q&A pair:", error);
      toast.error("Failed to delete Q&A pair");
    }
  };

  const handleEditEntry = (entry, e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    setEditingEntry(entry);
    setEditQuestion(entry.question || entry.question_ar || entry.question_en || entry.question_fr || "");
    setEditAnswer(entry.answer || entry.answer_ar || entry.answer_en || entry.answer_fr || "");
    setEditCategory(entry.category || "general");
  };

  const handleCancelEdit = () => {
    setEditingEntry(null);
    setEditQuestion("");
    setEditAnswer("");
    setEditCategory("general");
  };

  const handleSaveEdit = async () => {
    if (!editQuestion.trim() || !editAnswer.trim()) {
      toast.error("Please fill in both question and answer");
      return;
    }

    try {
      console.log("💾 Saving edited Q&A pair:", editingEntry.id);

      const updates = {
        question: editQuestion,
        answer: editAnswer,
        category: editCategory,
      };

      console.log("💾 Update data:", updates);

      const response = await updateLocalQAPair(editingEntry.id, updates);
      console.log("💾 Update response:", response);

      if (response.success) {
        // Reload data from backend
        await loadTrainingData(selectedLanguage);
        await loadStatistics();

        // Reset edit state
        handleCancelEdit();

        toast.success("✅ Q&A pair updated successfully!");
      } else {
        toast.error(response.error || "Failed to update Q&A pair");
      }
    } catch (error) {
      console.error("❌ Failed to update Q&A pair:", error);
      toast.error("Failed to update Q&A pair");
    }
  };

  const getLanguageFlag = (lang) => {
    const flags = {
      ar: "🇸🇦",
      en: "🇺🇸",
      fr: "🇫🇷",
      franco: "🔤",
    };
    return flags[lang] || "🌐";
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="text-center"
      >
        <h1 className="text-4xl font-bold gradient-text font-display mb-4">
          AI Training Center
        </h1>
        <p className="text-xl text-slate-600 max-w-2xl mx-auto">
          اكتب السؤال والجواب بالفرانكو — يتم الترجمة تلقائياً للعربية، الإنجليزية والفرنسية
        </p>
      </motion.div>

      {/* Stats */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="grid grid-cols-1 md:grid-cols-4 gap-6"
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="card glow-on-hover"
        >
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-slate-100">
              <BookOpenIcon className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-600">
                Total Entries
              </p>
              <p className="text-xl font-bold text-blue-600">
                {statistics.total}
              </p>
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.4 }}
          className="card glow-on-hover"
        >
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-slate-100">
              <SparklesIcon className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-600">Arabic</p>
              <p className="text-xl font-bold text-green-600">
                {statistics.by_language?.ar || 0}
              </p>
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.5 }}
          className="card glow-on-hover"
        >
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-slate-100">
              <SparklesIcon className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-600">English</p>
              <p className="text-xl font-bold text-purple-600">
                {statistics.by_language?.en || 0}
              </p>
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.6 }}
          className="card glow-on-hover"
        >
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-slate-100">
              <CheckCircleIcon className="w-5 h-5 text-orange-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-600">Categories</p>
              <p className="text-xl font-bold text-orange-600">
                {Object.keys(statistics.by_category || {}).length}
              </p>
            </div>
          </div>
        </motion.div>
      </motion.div>

      {/* Tabs - scroll horizontally on small screens */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.4 }}
        className="flex justify-center w-full overflow-x-auto pb-2 -mx-2 px-2"
      >
        <div className="glass rounded-2xl p-2 inline-flex space-x-2 flex-shrink-0">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative flex items-center space-x-2 px-6 py-3 rounded-xl font-medium transition-all duration-200 ${
                activeTab === tab.id
                  ? "text-white shadow-lg"
                  : "text-slate-600 hover:text-slate-800 hover:bg-white/50"
              }`}
            >
              {activeTab === tab.id && (
                <motion.div
                  layoutId="activeTrainingTab"
                  className={`absolute inset-0 bg-gradient-to-r ${tab.color} rounded-xl`}
                  transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                />
              )}
              <tab.icon className="w-5 h-5 relative z-10" />
              <span className="relative z-10">{tab.name}</span>
            </button>
          ))}
        </div>
      </motion.div>

      {/* Content */}
      <AnimatePresence mode="wait">
        {activeTab === "add" && (
          <motion.div
            key="add"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            className="max-w-4xl mx-auto"
          >
            <div className="card">
              <h2 className="text-xl font-bold text-slate-800 font-display mb-6 flex items-center">
                <AcademicCapIcon className="w-6 h-6 mr-2 text-green-600" />
                Add New Training Data
              </h2>

              <div className="space-y-6">
                {/* Question Input - Franco only */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    🔤 السؤال (Franco)
                  </label>
                  <textarea
                    value={newQuestion}
                    onChange={(e) => setNewQuestion(e.target.value)}
                    placeholder="e.g. kif fina n7afza? / chou el as3ar? / wen el 3emara?"
                    className="input-field w-full h-24 resize-none"
                  />
                  <p className="text-xs text-slate-500 mt-1">
                    اكتب بالفرانكو — يتم الترجمة تلقائياً للعربية، الإنجليزية والفرنسية
                  </p>
                </div>

                {/* Answer Input - Franco only */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    🔤 الجواب (Franco)
                  </label>
                  <textarea
                    value={newAnswer}
                    onChange={(e) => setNewAnswer(e.target.value)}
                    placeholder="e.g. el as3ar mawjouda 3al site..."
                    className="input-field w-full h-32 resize-none"
                  />
                </div>

                {/* Category Selection */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Category
                  </label>
                  <select
                    value={selectedCategory}
                    onChange={(e) => setSelectedCategory(e.target.value)}
                    className="input-field w-full"
                  >
                    {categories.map((cat) => (
                      <option key={cat.value} value={cat.value}>
                        {cat.emoji} {cat.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Submit Button */}
                <button
                  onClick={handleAddTraining}
                  disabled={loading || !newQuestion.trim() || !newAnswer.trim()}
                  className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <div className="flex items-center justify-center">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Saving...
                    </div>
                  ) : (
                    <>
                      <PlusIcon className="w-4 h-4 mr-2" />
                      Save Q&A Pair
                    </>
                  )}
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {activeTab === "manage" && (
          <motion.div
            key="manage"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            className="space-y-6"
          >
            <div className="card">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
                <h2 className="text-xl font-bold text-slate-800 font-display flex items-center">
                  <BookOpenIcon className="w-6 h-6 mr-2 text-blue-600" />
                  Manage Data ({trainingEntries.length})
                </h2>

                <div className="flex items-center gap-3 flex-wrap">
                  {/* Language section tabs */}
                  <div className="flex gap-1 p-1 bg-slate-100 rounded-lg flex-wrap">
                    {(() => {
                      const langMeta = { ar: ["عربي", "🇸🇦"], en: ["English", "🇺🇸"], fr: ["Français", "🇫🇷"], de: ["Deutsch", "🇩🇪"], es: ["Español", "🇪🇸"], tr: ["Türkçe", "🇹🇷"] };
                      const getMeta = (k) => langMeta[k] ? { label: langMeta[k][0], flag: langMeta[k][1] } : { label: k.toUpperCase(), flag: "🌐" };
                      const extraLangs = [...new Set(
                        trainingEntries.flatMap((e) =>
                          Object.keys(e).map((k) => k.match(/^question_(.+)$/)?.[1]).filter(Boolean).filter((l) => !["ar", "en", "fr"].includes(l))
                        )
                      )];
                      return [
                        { id: "all", label: "All", flag: "🌐" },
                        { id: "ar", ...getMeta("ar") },
                        { id: "en", ...getMeta("en") },
                        { id: "fr", ...getMeta("fr") },
                        ...extraLangs.map((id) => ({ id, ...getMeta(id) })),
                      ];
                    })().map(({ id, label, flag }) => (
                      <button
                        key={id}
                        onClick={() => setManageViewLang(id)}
                        className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                          manageViewLang === id
                            ? "bg-white shadow text-blue-600"
                            : "text-slate-600 hover:text-slate-800"
                        }`}
                      >
                        {flag} {label}
                      </button>
                    ))}
                  </div>
                  {/* Search */}
                  <div className="relative">
                    <MagnifyingGlassIcon className="w-5 h-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search..."
                      className="input-field pl-10 w-48 sm:w-64"
                    />
                  </div>
                </div>
              </div>

              {/* Delete Confirmation Modal */}
              <AnimatePresence>
                {deleteConfirmEntry && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
                    onClick={() => setDeleteConfirmEntry(null)}
                  >
                    <motion.div
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.9, opacity: 0 }}
                      className="card max-w-md w-full"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="text-center">
                        <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-red-100 mb-4">
                          <TrashIcon className="h-6 w-6 text-red-600" />
                        </div>

                        <h3 className="text-lg font-bold text-slate-900 mb-2">
                          Delete Q&A Pair
                        </h3>

                        <p className="text-sm text-slate-600 mb-6">
                          Are you sure you want to permanently delete this Q&A
                          pair? This action cannot be undone.
                        </p>

                        <div className="bg-slate-50 rounded-lg p-3 mb-6 text-left">
                          <p className="text-xs font-medium text-slate-500 mb-1">Question:</p>
                          <p className="text-sm text-slate-800 mb-2 line-clamp-2">
                            {deleteConfirmEntry.question || deleteConfirmEntry.question_ar || deleteConfirmEntry.question_en || deleteConfirmEntry.question_fr || "—"}
                          </p>
                          <p className="text-xs font-medium text-slate-500 mb-1">Answer:</p>
                          <p className="text-sm text-slate-700 line-clamp-2">
                            {deleteConfirmEntry.answer || deleteConfirmEntry.answer_ar || deleteConfirmEntry.answer_en || deleteConfirmEntry.answer_fr || "—"}
                          </p>
                        </div>

                        <div className="flex space-x-3">
                          <button
                            onClick={() => setDeleteConfirmEntry(null)}
                            className="btn-ghost flex-1"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={handleDeleteEntry}
                            disabled={loading}
                            className="flex-1 px-4 py-2 bg-red-600 text-white rounded-xl font-medium hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {loading ? (
                              <div className="flex items-center justify-center">
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                                Deleting...
                              </div>
                            ) : (
                              "Delete"
                            )}
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Edit Modal */}
              <AnimatePresence>
                {editingEntry && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
                    onClick={handleCancelEdit}
                  >
                    <motion.div
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.9, opacity: 0 }}
                      className="card max-w-2xl w-full max-h-[90vh] overflow-y-auto"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex items-center justify-between mb-6">
                        <h3 className="text-xl font-bold text-slate-800 font-display flex items-center">
                          <PencilIcon className="w-6 h-6 mr-2 text-blue-600" />
                          Edit Q&A Pair
                        </h3>
                        <button
                          onClick={handleCancelEdit}
                          className="p-2 text-slate-400 hover:text-slate-600 transition-colors"
                        >
                          <XCircleIcon className="w-6 h-6" />
                        </button>
                      </div>

                      <div className="space-y-6">
                        {/* Question Input - Franco for structured, any for legacy */}
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-2">
                            {editingEntry?.question_ar ? "🔤 السؤال (Franco)" : "Question"}
                          </label>
                          <textarea
                            value={editQuestion}
                            onChange={(e) => setEditQuestion(e.target.value)}
                            placeholder={editingEntry?.question_ar ? "e.g. kif fina n7afza?" : "Enter the question..."}
                            className="input-field w-full h-24 resize-none"
                          />
                          {editingEntry?.question_ar && (
                            <p className="text-xs text-slate-500 mt-1">يُعاد الترجمة تلقائياً للعربية، الإنجليزية والفرنسية</p>
                          )}
                        </div>

                        {/* Answer Input */}
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-2">
                            {editingEntry?.question_ar ? "🔤 الجواب (Franco)" : "Answer"}
                          </label>
                          <textarea
                            value={editAnswer}
                            onChange={(e) => setEditAnswer(e.target.value)}
                            placeholder={editingEntry?.question_ar ? "e.g. el as3ar mawjouda..." : "Enter the answer..."}
                            className="input-field w-full h-32 resize-none"
                          />
                        </div>

                        {/* Category Selection */}
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-2">
                            Category
                          </label>
                          <select
                            value={editCategory}
                            onChange={(e) => setEditCategory(e.target.value)}
                            className="input-field w-full"
                          >
                            {categories.map((cat) => (
                              <option key={cat.value} value={cat.value}>
                                {cat.emoji} {cat.label}
                              </option>
                            ))}
                          </select>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex space-x-4">
                          <button
                            onClick={handleSaveEdit}
                            disabled={
                              loading ||
                              !editQuestion.trim() ||
                              !editAnswer.trim()
                            }
                            className="btn-primary flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {loading ? (
                              <div className="flex items-center justify-center">
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                                Saving...
                              </div>
                            ) : (
                              <>
                                <CheckCircleIcon className="w-4 h-4 mr-2" />
                                Save Changes
                              </>
                            )}
                          </button>
                          <button
                            onClick={handleCancelEdit}
                            className="btn-ghost flex-1"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="space-y-4 max-h-96 overflow-y-auto scrollbar-hide">
                <AnimatePresence>
                  {filteredEntries.length === 0 ? (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="text-center py-12"
                    >
                      <BookOpenIcon className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                      <p className="text-slate-500">
                        {searchQuery
                          ? "No entries match your search"
                          : manageViewLang === "all"
                          ? "No training data yet"
                          : `No ${manageViewLang.toUpperCase()} entries yet`}
                      </p>
                      <p className="text-sm text-slate-400 mt-1">
                        {searchQuery
                          ? "Try a different search term"
                          : "Add some training data to get started"}
                      </p>
                    </motion.div>
                  ) : (
                    filteredEntries.map((entry, idx) => {
                      const hasStructured = entry.question_ar || entry.question_en || entry.question_fr;
                      const langMeta = { ar: ["عربي", "🇸🇦"], en: ["English", "🇺🇸"], fr: ["Français", "🇫🇷"], de: ["Deutsch", "🇩🇪"], es: ["Español", "🇪🇸"], tr: ["Türkçe", "🇹🇷"] };
                      const getMeta = (k) => langMeta[k] ? { label: langMeta[k][0], flag: langMeta[k][1] } : { label: k.toUpperCase(), flag: "🌐" };
                      let langs = [
                        { key: "ar", ...getMeta("ar"), q: entry.question_ar || entry.question, a: entry.answer_ar || entry.answer },
                        { key: "en", ...getMeta("en"), q: entry.question_en || entry.question, a: entry.answer_en || entry.answer },
                        { key: "fr", ...getMeta("fr"), q: entry.question_fr || entry.question, a: entry.answer_fr || entry.answer },
                      ];
                      Object.keys(entry).forEach((k) => {
                        const m = k.match(/^question_(.+)$/);
                        if (m && !["ar", "en", "fr"].includes(m[1]) && entry[k]) {
                          langs.push({ key: m[1], ...getMeta(m[1]), q: entry[k], a: entry[`answer_${m[1]}`] || "" });
                        }
                      });
                      const displayLangs = manageViewLang === "all" ? langs : langs.filter((l) => l.key === manageViewLang);
                      const hasContent = displayLangs.some((l) => l.q || l.a);
                      const entryLang = entry.language || "ar";
                      if (manageViewLang !== "all" && !hasStructured && entryLang !== manageViewLang) return null;
                      if (!hasContent && manageViewLang !== "all") return null;
                      return (
                      <motion.div
                        key={entry.id || idx}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        transition={{ duration: 0.3 }}
                        className="glass rounded-xl p-4 hover:shadow-lg transition-all duration-200"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1 space-y-3">
                            <div className="flex items-center space-x-2 flex-wrap">
                              <span className="text-xs px-2 py-1 rounded-full bg-blue-100 text-blue-700">
                                {entry.category || "general"}
                              </span>
                              {entry.timestamp && (
                                <span className="text-xs text-slate-400">
                                  {new Date(entry.timestamp).toLocaleDateString()}
                                </span>
                              )}
                            </div>

                            {hasStructured ? (
                              <div className="space-y-2">
                                {displayLangs.map(({ key, label, flag, q, a }) => (q || a) && (
                                  <div key={key} className="border border-slate-200 rounded-lg p-3">
                                    <p className="text-xs font-medium text-slate-500 mb-1 flex items-center gap-1">
                                      <span>{flag}</span> {label}
                                    </p>
                                    <p className="text-slate-700 text-sm mb-1"><strong>Q:</strong> {q || "—"}</p>
                                    <p className="text-slate-600 text-sm"><strong>A:</strong> {a || "—"}</p>
                                  </div>
                                ))}
                              </div>
                            ) : (
                            <>
                              <div>
                                <p className="text-sm font-medium text-slate-600 mb-1">Question:</p>
                                <p className="text-slate-800 bg-slate-50 rounded p-2 text-sm">
                                  {entry.question}
                                </p>
                              </div>
                              <div>
                                <p className="text-sm font-medium text-slate-600 mb-1">Answer:</p>
                                <p className="text-slate-700 bg-green-50 rounded p-2 text-sm">
                                  {entry.answer}
                                </p>
                              </div>
                            </>
                            )}
                          </div>

                          <div className="flex space-x-2 ml-4">
                            <button
                              onClick={(e) => handleEditEntry(entry, e)}
                              className="p-2 text-slate-400 hover:text-blue-600 transition-colors rounded-lg hover:bg-blue-50"
                              title="Edit Q&A pair"
                            >
                              <PencilIcon className="w-4 h-4" />
                            </button>
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                setDeleteConfirmEntry(entry);
                              }}
                              className="p-2 text-slate-400 hover:text-red-600 transition-colors rounded-lg hover:bg-red-50"
                              title="Delete Q&A pair"
                            >
                              <TrashIcon className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                      </motion.div>
                    );
                    })
                  )}
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        )}



        {activeTab === "knowledge_base" && (
          <ContentFilesPanel
            section="knowledge"
            sectionName="Knowledge Base"
            icon={BookOpenIcon}
          />
        )}

        {activeTab === "style_guide" && (
          <ContentFilesPanel
            section="style"
            sectionName="Style Guide"
            icon={SparklesIcon}
          />
        )}

        {activeTab === "price_list" && (
          <ContentFilesPanel
            section="price"
            sectionName="Price List"
            icon={CurrencyDollarIcon}
          />
        )}

        {activeTab === "retrieval_debug" && (
          <motion.div
            key="retrieval_debug"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            className="space-y-4"
          >
            <div className="card">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-slate-800 font-display flex items-center">
                  <BugAntIcon className="w-6 h-6 mr-2 text-amber-600" />
                  Retrieval Debug Logs
                </h2>
                <button
                  onClick={loadRetrievalLogs}
                  disabled={retrievalLogsLoading}
                  className="btn-ghost flex items-center gap-2"
                >
                  <ArrowPathIcon className={`w-5 h-5 ${retrievalLogsLoading ? "animate-spin" : ""}`} />
                  Refresh
                </button>
              </div>
              <p className="text-sm text-slate-600 mb-4">
                Smart retrieval logs (requires SMART_RETRIEVAL_DEBUG=1 on server). Auto-refreshes every 10s.
              </p>
              {retrievalLogsLoading && retrievalLogs.length === 0 ? (
                <div className="text-center py-12 text-slate-500">Loading logs...</div>
              ) : retrievalLogs.length === 0 ? (
                <div className="text-center py-12 text-slate-500">
                  No logs yet. Enable SMART_RETRIEVAL_DEBUG=1 on the server and send messages to the bot.
                </div>
              ) : (
                <div className="space-y-3 max-h-[500px] overflow-y-auto scrollbar-hide">
                  {retrievalLogs.map((log, idx) => (
                    <div
                      key={idx}
                      className="border border-slate-200 rounded-lg p-3 text-left text-sm font-mono bg-slate-50"
                    >
                      <div className="flex flex-wrap gap-2 mb-2">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          log.source === "faq" ? "bg-green-100 text-green-800" : "bg-blue-100 text-blue-800"
                        }`}>
                          {log.source || "ai"}
                        </span>
                        {log.faq_matched && <span className="px-2 py-0.5 rounded text-xs bg-green-100 text-green-800">FAQ</span>}
                        <span className="text-slate-400 text-xs">{log.timestamp}</span>
                      </div>
                      <p className="text-slate-700 break-words mb-1"><strong>Message:</strong> {log.user_message}</p>
                      <p className="text-slate-600 text-xs">Intent: {log.detected_intent} | Gender: {log.detected_gender}</p>
                      {log.faq_match_score != null && <p className="text-xs text-slate-500">FAQ score: {log.faq_match_score}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default Training;
