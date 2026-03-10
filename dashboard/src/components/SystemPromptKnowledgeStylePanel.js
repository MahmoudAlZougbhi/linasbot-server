import React, { useCallback, useEffect, useState } from "react";
import { ArrowPathIcon, ClipboardDocumentIcon } from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import toast from "react-hot-toast";

const SystemPromptKnowledgeStylePanel = () => {
  const { getSystemPromptKnowledgeStyle } = useApi();
  const [loading, setLoading] = useState(false);
  const [promptText, setPromptText] = useState("");
  const [meta, setMeta] = useState({
    style_files_count: 0,
    knowledge_files_count: 0,
    total_chars: 0,
  });

  const loadPrompt = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getSystemPromptKnowledgeStyle();
      if (res?.success && res?.data) {
        setPromptText(res.data.system_prompt_knowledge_style || "");
        setMeta({
          style_files_count: res.data.style_files_count || 0,
          knowledge_files_count: res.data.knowledge_files_count || 0,
          total_chars: res.data.total_chars || 0,
        });
      } else {
        toast.error(res?.error || "Failed to load system prompt");
      }
    } catch (error) {
      toast.error("Failed to load system prompt");
    } finally {
      setLoading(false);
    }
  }, [getSystemPromptKnowledgeStyle]);

  useEffect(() => {
    loadPrompt();
  }, [loadPrompt]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(promptText || "");
      toast.success("System prompt copied");
    } catch (error) {
      toast.error("Failed to copy");
    }
  };

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="font-semibold text-slate-800">System Prompt (Knowledge + Style)</h3>
            <p className="text-sm text-slate-600 mt-1">
              Read-only merged text from Content Managers (Knowledge and Style files).
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={loadPrompt}
              disabled={loading}
              className="px-3 py-2 rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-50 flex items-center gap-2"
            >
              <ArrowPathIcon className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              onClick={handleCopy}
              disabled={!promptText}
              className="px-3 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
            >
              <ClipboardDocumentIcon className="w-4 h-4" />
              Copy
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          <div className="rounded-lg bg-slate-50 p-3 border border-slate-200">
            <p className="text-xs text-slate-500">Style files</p>
            <p className="text-xl font-semibold text-slate-800">{meta.style_files_count}</p>
          </div>
          <div className="rounded-lg bg-slate-50 p-3 border border-slate-200">
            <p className="text-xs text-slate-500">Knowledge files</p>
            <p className="text-xl font-semibold text-slate-800">{meta.knowledge_files_count}</p>
          </div>
          <div className="rounded-lg bg-slate-50 p-3 border border-slate-200">
            <p className="text-xs text-slate-500">Characters</p>
            <p className="text-xl font-semibold text-slate-800">{meta.total_chars}</p>
          </div>
        </div>

        <textarea
          readOnly
          value={promptText}
          className="w-full h-[32rem] p-4 border border-slate-200 rounded-lg font-mono text-sm resize-none bg-slate-50"
          placeholder={loading ? "Loading..." : "No content yet"}
        />
      </div>
    </div>
  );
};

export default SystemPromptKnowledgeStylePanel;
