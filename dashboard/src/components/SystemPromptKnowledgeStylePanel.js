import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowPathIcon, CheckCircleIcon } from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import toast from "react-hot-toast";

const SystemPromptKnowledgeStylePanel = () => {
  const { getTrainingFile, updateTrainingFile, loading } = useApi();

  const [knowledgeContent, setKnowledgeContent] = useState("");
  const [styleContent, setStyleContent] = useState("");
  const [trainedQaContent, setTrainedQaContent] = useState("");
  const [originalKnowledge, setOriginalKnowledge] = useState("");
  const [originalStyle, setOriginalStyle] = useState("");
  const [originalTrainedQa, setOriginalTrainedQa] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const loadFiles = useCallback(async () => {
    try {
      setRefreshing(true);
      const [knowledgeRes, styleRes, trainedQaRes] = await Promise.all([
        getTrainingFile("knowledge_base"),
        getTrainingFile("style_guide"),
        getTrainingFile("trained_qa_reference"),
      ]);

      if (knowledgeRes?.success) {
        const text = knowledgeRes.content || "";
        setKnowledgeContent(text);
        setOriginalKnowledge(text);
      } else {
        toast.error(knowledgeRes?.error || "Failed to load knowledge base");
      }

      if (styleRes?.success) {
        const text = styleRes.content || "";
        setStyleContent(text);
        setOriginalStyle(text);
      } else {
        toast.error(styleRes?.error || "Failed to load style guide");
      }

      if (trainedQaRes?.success) {
        const text = trainedQaRes.content || "";
        setTrainedQaContent(text);
        setOriginalTrainedQa(text);
      } else {
        toast.error(trainedQaRes?.error || "Failed to load trained Q&A reference");
      }
    } catch (error) {
      toast.error("Failed to load system prompt sources");
    } finally {
      setRefreshing(false);
    }
  }, [getTrainingFile]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const hasKnowledgeChanges = useMemo(
    () => knowledgeContent !== originalKnowledge,
    [knowledgeContent, originalKnowledge]
  );
  const hasStyleChanges = useMemo(
    () => styleContent !== originalStyle,
    [styleContent, originalStyle]
  );
  const hasTrainedQaChanges = useMemo(
    () => trainedQaContent !== originalTrainedQa,
    [trainedQaContent, originalTrainedQa]
  );

  const handleSaveKnowledge = async () => {
    const res = await updateTrainingFile("knowledge_base", knowledgeContent);
    if (res?.success) {
      setOriginalKnowledge(knowledgeContent);
    }
  };

  const handleSaveStyle = async () => {
    const res = await updateTrainingFile("style_guide", styleContent);
    if (res?.success) {
      setOriginalStyle(styleContent);
    }
  };

  const handleSaveTrainedQa = async () => {
    const res = await updateTrainingFile("trained_qa_reference", trainedQaContent);
    if (res?.success) {
      setOriginalTrainedQa(trainedQaContent);
    }
  };

  return (
    <div className="space-y-6">
      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div>
            <h3 className="font-semibold text-slate-800">
              System Prompt Sources (Actual Runtime Files)
            </h3>
            <p className="text-sm text-slate-600 mt-1">
              Edit the exact files used in system prompt composition:{" "}
              <code>knowledge_base.txt</code>, <code>style_guide.txt</code>, and{" "}
              <code>trained_qa_reference.txt</code>.
            </p>
          </div>
          <button
            onClick={loadFiles}
            disabled={refreshing}
            className="px-3 py-2 rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-50 flex items-center gap-2"
          >
            <ArrowPathIcon className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h4 className="font-semibold text-slate-800">Knowledge Base (system prompt)</h4>
          <button
            onClick={handleSaveKnowledge}
            disabled={loading || !hasKnowledgeChanges}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
          >
            <CheckCircleIcon className="w-4 h-4" />
            Save Knowledge
          </button>
        </div>
        <textarea
          value={knowledgeContent}
          onChange={(e) => setKnowledgeContent(e.target.value)}
          className="w-full h-80 p-4 border border-slate-200 rounded-lg font-mono text-sm resize-none"
          placeholder="knowledge_base.txt content..."
        />
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h4 className="font-semibold text-slate-800">Style Guide (system prompt)</h4>
          <button
            onClick={handleSaveStyle}
            disabled={loading || !hasStyleChanges}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
          >
            <CheckCircleIcon className="w-4 h-4" />
            Save Style
          </button>
        </div>
        <textarea
          value={styleContent}
          onChange={(e) => setStyleContent(e.target.value)}
          className="w-full h-80 p-4 border border-slate-200 rounded-lg font-mono text-sm resize-none"
          placeholder="style_guide.txt content..."
        />
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h4 className="font-semibold text-slate-800">Trained Q&A Reference (system prompt)</h4>
          <button
            onClick={handleSaveTrainedQa}
            disabled={loading || !hasTrainedQaChanges}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
          >
            <CheckCircleIcon className="w-4 h-4" />
            Save Trained Q&A
          </button>
        </div>
        <textarea
          value={trainedQaContent}
          onChange={(e) => setTrainedQaContent(e.target.value)}
          className="w-full h-80 p-4 border border-slate-200 rounded-lg font-mono text-sm resize-none"
          placeholder="trained_qa_reference.txt content..."
        />
      </div>
    </div>
  );
};

export default SystemPromptKnowledgeStylePanel;
