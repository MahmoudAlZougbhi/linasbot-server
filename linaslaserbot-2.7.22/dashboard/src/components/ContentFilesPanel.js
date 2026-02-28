import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  DocumentTextIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import toast from "react-hot-toast";

const ContentFilesPanel = ({ section, sectionName, icon: Icon }) => {
  const {
    getContentFilesList,
    getContentFile,
    createContentFile,
    updateContentFile,
    deleteContentFile,
  } = useApi();

  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(null);
  const [loading, setLoading] = useState(false);

  // Create form
  const [newTitle, setNewTitle] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newTags, setNewTags] = useState("");
  const [newLanguage, setNewLanguage] = useState("");
  const [newAudience, setNewAudience] = useState("");
  const [newPriority, setNewPriority] = useState("");

  const loadFiles = async () => {
    try {
      const res = await getContentFilesList(section);
      if (res.success && res.data) {
        setFiles(res.data);
      } else {
        setFiles([]);
      }
    } catch (e) {
      console.error("Failed to load files:", e);
      setFiles([]);
    }
  };

  useEffect(() => {
    loadFiles();
  }, [section]);

  const handleSelectFile = async (file) => {
    try {
      setLoading(true);
      const res = await getContentFile(section, file.id);
      if (res.success && res.data) {
        setSelectedFile(res.data);
        setFileContent(res.data.content || "");
      }
    } catch (e) {
      toast.error("Failed to load file");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!selectedFile) return;
    try {
      setLoading(true);
      const res = await updateContentFile(section, selectedFile.id, {
        content: fileContent,
        title: selectedFile.title,
      });
      if (res.success) {
        setSelectedFile({ ...selectedFile, content: fileContent });
        await loadFiles();
        toast.success("File updated!");
      } else {
        toast.error(res.error || "Update failed");
      }
    } catch (e) {
      toast.error("Failed to update");
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!newTitle.trim()) {
      toast.error("Title is required");
      return;
    }
    try {
      setLoading(true);
      const tags = newTags ? newTags.split(",").map((t) => t.trim()).filter(Boolean) : [];
      const payload = {
        title: newTitle.trim(),
        content: newContent,
        tags,
        language: newLanguage || undefined,
      };
      if (newAudience) payload.audience = newAudience;
      if (newPriority) payload.priority = parseInt(newPriority, 10) || undefined;
      const res = await createContentFile(section, payload);
      if (res.success) {
        setShowCreateModal(false);
        setNewTitle("");
        setNewContent("");
        setNewTags("");
        setNewLanguage("");
        setNewAudience("");
        setNewPriority("");
        await loadFiles();
        toast.success("File created!");
      } else {
        toast.error(res.error || "Create failed");
      }
    } catch (e) {
      toast.error("Failed to create");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!showDeleteConfirm) return;
    try {
      setLoading(true);
      const res = await deleteContentFile(section, showDeleteConfirm.id);
      if (res.success) {
        setShowDeleteConfirm(null);
        if (selectedFile?.id === showDeleteConfirm.id) {
          setSelectedFile(null);
          setFileContent("");
        }
        await loadFiles();
        toast.success("File deleted!");
      } else {
        toast.error(res.error || "Delete failed");
      }
    } catch (e) {
      toast.error("Failed to delete");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex gap-6">
      {/* File list */}
      <div className="w-72 shrink-0 card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-slate-800 flex items-center gap-2">
            <Icon className="w-5 h-5 text-blue-600" />
            {sectionName} Files
          </h3>
          <button
            onClick={() => setShowCreateModal(true)}
            className="p-2 rounded-lg bg-blue-100 text-blue-600 hover:bg-blue-200 transition"
            title="Create File"
          >
            <PlusIcon className="w-5 h-5" />
          </button>
        </div>
        <ul className="space-y-2 max-h-96 overflow-y-auto">
          {files.length === 0 && (
            <li className="text-slate-500 text-sm py-4 text-center">
              No files yet. Click + to create.
            </li>
          )}
          {files.map((f) => (
            <li
              key={f.id}
              className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition ${
                selectedFile?.id === f.id ? "bg-blue-50 border border-blue-200" : "hover:bg-slate-50"
              }`}
            >
              <div
                className="flex-1 min-w-0"
                onClick={() => handleSelectFile(f)}
              >
                <p className="font-medium text-slate-800 truncate">{f.title || "Untitled"}</p>
                {f.tags?.length > 0 && (
                  <p className="text-xs text-slate-500 truncate">{f.tags.join(", ")}</p>
                )}
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setShowDeleteConfirm(f);
                }}
                className="p-1 text-red-500 hover:bg-red-50 rounded"
              >
                <TrashIcon className="w-4 h-4" />
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* Editor */}
      <div className="flex-1 card min-w-0">
        {selectedFile ? (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-800">{selectedFile.title}</h3>
              <button
                onClick={handleSaveEdit}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                Save
              </button>
            </div>
            <textarea
              value={fileContent}
              onChange={(e) => setFileContent(e.target.value)}
              className="w-full h-96 p-4 border border-slate-200 rounded-lg font-mono text-sm resize-none"
              placeholder="File content..."
            />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-96 text-slate-500">
            <DocumentTextIcon className="w-16 h-16 mb-4 opacity-50" />
            <p>Select a file or create a new one</p>
          </div>
        )}
      </div>

      {/* Create modal */}
      <AnimatePresence>
        {showCreateModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
            onClick={() => setShowCreateModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.95 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold">Create {sectionName} File</h3>
                <button onClick={() => setShowCreateModal(false)} className="p-1 hover:bg-slate-100 rounded">
                  <XMarkIcon className="w-5 h-5" />
                </button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Title *</label>
                  <input
                    type="text"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg"
                    placeholder="e.g. Laser Hair Removal for Men"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Content</label>
                  <textarea
                    value={newContent}
                    onChange={(e) => setNewContent(e.target.value)}
                    className="w-full h-40 px-3 py-2 border border-slate-200 rounded-lg resize-none"
                    placeholder="File content..."
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Tags (comma-separated)</label>
                  <input
                    type="text"
                    value={newTags}
                    onChange={(e) => setNewTags(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg"
                    placeholder="men, hair removal, laser"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Language (optional)</label>
                  <input
                    type="text"
                    value={newLanguage}
                    onChange={(e) => setNewLanguage(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg"
                    placeholder="ar, en, fr"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Audience</label>
                    <select
                      value={newAudience}
                      onChange={(e) => setNewAudience(e.target.value)}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg"
                    >
                      <option value="">general</option>
                      <option value="men">men</option>
                      <option value="women">women</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Priority (1-5)</label>
                    <input
                      type="number"
                      min="1"
                      max="5"
                      value={newPriority}
                      onChange={(e) => setNewPriority(e.target.value)}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg"
                      placeholder="3"
                    />
                  </div>
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-6">
                <button onClick={() => setShowCreateModal(false)} className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg">
                  Cancel
                </button>
                <button onClick={handleCreate} disabled={loading} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
                  Create
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Delete confirm */}
      <AnimatePresence>
        {showDeleteConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
            onClick={() => setShowDeleteConfirm(null)}
          >
            <motion.div
              initial={{ scale: 0.95 }}
              animate={{ scale: 1 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white rounded-xl shadow-xl max-w-md w-full p-6"
            >
              <p className="text-slate-700 mb-4">Delete &quot;{showDeleteConfirm.title}&quot;?</p>
              <div className="flex justify-end gap-2">
                <button onClick={() => setShowDeleteConfirm(null)} className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg">Cancel</button>
                <button onClick={handleDelete} disabled={loading} className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50">Delete</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ContentFilesPanel;
