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
} from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import toast from "react-hot-toast";

import TrainingFileEditor from "../components/TrainingFileEditor";

const Training = () => {
  const {
    getLocalQAPairs,
    createLocalQAPair,
    updateLocalQAPair,
    deleteLocalQAPair,
    getLocalQAStatistics,
    loading,
  } = useApi();

  const [activeTab, setActiveTab] = useState("add");
  const [trainingEntries, setTrainingEntries] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [filteredEntries, setFilteredEntries] = useState([]);
  const [statistics, setStatistics] = useState({
    total: 0,
    by_language: {},
    by_category: {},
  });

  // Add training form
  const [newQuestion, setNewQuestion] = useState("");
  const [newAnswer, setNewAnswer] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("general");

  // Edit mode state
  const [editingEntry, setEditingEntry] = useState(null);
  const [editQuestion, setEditQuestion] = useState("");
  const [editAnswer, setEditAnswer] = useState("");
  const [editCategory, setEditCategory] = useState("general");

  // Delete confirmation modal state
  const [deleteConfirmEntry, setDeleteConfirmEntry] = useState(null);

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
    loadTrainingData();
    loadStatistics();
  }, []);

  useEffect(() => {
    if (searchQuery.trim()) {
      const filtered = trainingEntries.filter(
        (entry) =>
          entry.question.toLowerCase().includes(searchQuery.toLowerCase()) ||
          entry.answer.toLowerCase().includes(searchQuery.toLowerCase())
      );
      setFilteredEntries(filtered);
    } else {
      setFilteredEntries(trainingEntries);
    }
  }, [searchQuery, trainingEntries]);

  const loadTrainingData = async () => {
    try {
      console.log("🔄 Loading Q&A pairs from local file...");
      const response = await getLocalQAPairs();

      console.log("📦 Response:", response);

      if (response.success && response.data) {
        console.log(`✅ Loaded ${response.data.length} Q&A pairs`);
        setTrainingEntries(response.data);
      } else {
        console.log("⚠️ No data or success=false");
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
      toast.error("Please fill in both question and answer");
      return;
    }

    try {
      console.log("💾 Saving Q&A pair...");
      console.log("   Question:", newQuestion);
      console.log("   Answer:", newAnswer);
      console.log("   Category:", selectedCategory);

      const qaData = {
        question: newQuestion,
        answer: newAnswer,
        category: selectedCategory,
      };

      const response = await createLocalQAPair(qaData);

      console.log("📤 Response:", response);

      if (response.success) {
        // Reload data from backend
        await loadTrainingData();
        await loadStatistics();

        // Reset form
        setNewQuestion("");
        setNewAnswer("");
        setSelectedCategory("general");

        toast.success(
          `✅ Q&A saved! Language detected: ${response.data.language}`
        );
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
        await loadTrainingData();
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
    console.log("✏️ Editing entry:", entry);
    setEditingEntry(entry);
    setEditQuestion(entry.question);
    setEditAnswer(entry.answer);
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
        await loadTrainingData();
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
          Teach your AI assistant new knowledge. Add Q&A pairs and the bot will
          automatically detect the language!
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

      {/* Tabs */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.4 }}
        className="flex justify-center"
      >
        <div className="glass rounded-2xl p-2 inline-flex space-x-2">
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
                {/* Question Input */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Question (any language)
                  </label>
                  <textarea
                    value={newQuestion}
                    onChange={(e) => setNewQuestion(e.target.value)}
                    placeholder="What question should the AI be able to answer?"
                    className="input-field w-full h-24 resize-none"
                  />
                  <p className="text-xs text-slate-500 mt-1">
                    💡 Language will be auto-detected from your question
                  </p>
                </div>

                {/* Answer Input */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Answer
                  </label>
                  <textarea
                    value={newAnswer}
                    onChange={(e) => setNewAnswer(e.target.value)}
                    placeholder="Provide the correct answer..."
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
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-slate-800 font-display flex items-center">
                  <BookOpenIcon className="w-6 h-6 mr-2 text-blue-600" />
                  Training Data ({trainingEntries.length})
                </h2>

                {/* Search */}
                <div className="relative">
                  <MagnifyingGlassIcon className="w-5 h-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search entries..."
                    className="input-field pl-10 w-64"
                  />
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
                          <p className="text-xs font-medium text-slate-500 mb-1">
                            Question:
                          </p>
                          <p className="text-sm text-slate-800 mb-2 line-clamp-2">
                            {deleteConfirmEntry.question}
                          </p>
                          <p className="text-xs font-medium text-slate-500 mb-1">
                            Answer:
                          </p>
                          <p className="text-sm text-slate-700 line-clamp-2">
                            {deleteConfirmEntry.answer}
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
                        {/* Question Input */}
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-2">
                            Question
                          </label>
                          <textarea
                            value={editQuestion}
                            onChange={(e) => setEditQuestion(e.target.value)}
                            placeholder="Enter the question..."
                            className="input-field w-full h-24 resize-none"
                          />
                        </div>

                        {/* Answer Input */}
                        <div>
                          <label className="block text-sm font-medium text-slate-700 mb-2">
                            Answer
                          </label>
                          <textarea
                            value={editAnswer}
                            onChange={(e) => setEditAnswer(e.target.value)}
                            placeholder="Enter the answer..."
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
                          : "No training data yet"}
                      </p>
                      <p className="text-sm text-slate-400 mt-1">
                        {searchQuery
                          ? "Try a different search term"
                          : "Add some training data to get started"}
                      </p>
                    </motion.div>
                  ) : (
                    filteredEntries.map((entry) => (
                      <motion.div
                        key={entry.id}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        transition={{ duration: 0.3 }}
                        className="glass rounded-xl p-4 hover:shadow-lg transition-all duration-200"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1 space-y-3">
                            <div className="flex items-center space-x-2">
                              <span className="text-lg">
                                {getLanguageFlag(entry.language)}
                              </span>
                              <span className="text-xs font-medium text-slate-500">
                                {entry.language?.toUpperCase()}
                              </span>
                              <span className="text-xs px-2 py-1 rounded-full bg-blue-100 text-blue-700">
                                {entry.category}
                              </span>
                              {entry.timestamp && (
                                <span className="text-xs text-slate-400">
                                  {new Date(
                                    entry.timestamp
                                  ).toLocaleDateString()}
                                </span>
                              )}
                            </div>

                            <div>
                              <p className="text-sm font-medium text-slate-600 mb-1">
                                Question:
                              </p>
                              <p className="text-slate-800 bg-slate-50 rounded p-2 text-sm">
                                {entry.question}
                              </p>
                            </div>

                            <div>
                              <p className="text-sm font-medium text-slate-600 mb-1">
                                Answer:
                              </p>
                              <p className="text-slate-700 bg-green-50 rounded p-2 text-sm">
                                {entry.answer}
                              </p>
                            </div>
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
                    ))
                  )}
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        )}



        {activeTab === "knowledge_base" && (
          <TrainingFileEditor
            fileId="knowledge_base"
            title="Knowledge Base"
            description="General knowledge and information the bot can reference"
          />
        )}

        {activeTab === "style_guide" && (
          <TrainingFileEditor
            fileId="style_guide"
            title="Style Guide"
            description="Bot behavior, tone, and response style guidelines"
          />
        )}

        {activeTab === "price_list" && (
          <TrainingFileEditor
            fileId="price_list"
            title="Price List"
            description="Service pricing information"
          />
        )}
      </AnimatePresence>
    </div>
  );
};

export default Training;
