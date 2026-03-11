import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowPathIcon, CheckCircleIcon } from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import toast from "react-hot-toast";

const SystemPromptKnowledgeStylePanel = () => {
  const { getTrainingFile, updateTrainingFile, loading } = useApi();

  const [knowledgeContent, setKnowledgeContent] = useState("");
  const [styleContent, setStyleContent] = useState("");
  const [templateContent, setTemplateContent] = useState("");
  const [originalKnowledge, setOriginalKnowledge] = useState("");
  const [originalStyle, setOriginalStyle] = useState("");
  const [originalTemplate, setOriginalTemplate] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const loadFiles = useCallback(async () => {
    try {
      setRefreshing(true);
      const [knowledgeRes, styleRes, templateRes] = await Promise.all([
        getTrainingFile("knowledge_base"),
        getTrainingFile("style_guide"),
        getTrainingFile("system_prompt_template"),
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

      if (templateRes?.success) {
        const text = templateRes.content || "";
        setTemplateContent(text);
        setOriginalTemplate(text);
      } else {
        toast.error(templateRes?.error || "Failed to load system prompt template");
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
  const hasTemplateChanges = useMemo(
    () => templateContent !== originalTemplate,
    [templateContent, originalTemplate]
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

  const handleSaveTemplate = async () => {
    const res = await updateTrainingFile("system_prompt_template", templateContent);
    if (res?.success) {
      setOriginalTemplate(templateContent);
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
              <code>system_prompt_template.txt</code>, <code>knowledge_base.txt</code>, and <code>style_guide.txt</code>.
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
          <h4 className="font-semibold text-slate-800">System Prompt Template (system prompt)</h4>
          <button
            onClick={handleSaveTemplate}
            disabled={loading || !hasTemplateChanges}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
          >
            <CheckCircleIcon className="w-4 h-4" />
            Save Template
          </button>
        </div>
        <textarea
          value={templateContent}
          onChange={(e) => setTemplateContent(e.target.value)}
          className="w-full h-80 p-4 border border-slate-200 rounded-lg font-mono text-sm resize-none"
          placeholder="system_prompt_template.txt content..."
        />
      </div>
    </div>
  );
};

export default SystemPromptKnowledgeStylePanel;
