import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  ArrowPathIcon,
  UserIcon,
  ChatBubbleLeftRightIcon,
  CpuChipIcon,
  ArrowRightIcon,
  ChevronDownIcon,
  ChevronUpIcon,
} from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";

const SOURCE_LABELS = {
  gpt: { label: "GPT", color: "bg-violet-100 text-violet-700", icon: "🤖" },
  qa_database: { label: "Q&A DB", color: "bg-emerald-100 text-emerald-700", icon: "📚" },
  dynamic_retrieval: { label: "Dynamic", color: "bg-amber-100 text-amber-700", icon: "📂" },
  rate_limit: { label: "Rate Limit", color: "bg-orange-100 text-orange-700", icon: "⏱" },
  moderation: { label: "Moderation", color: "bg-rose-100 text-rose-700", icon: "🛡" },
};

const FlowCard = ({ entry, isExpanded, onToggle }) => {
  const meta = SOURCE_LABELS[entry.source] || { label: entry.source, color: "bg-slate-100 text-slate-700", icon: "?" };
  const time = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString("ar-LB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="card overflow-hidden"
    >
      <div
        className="p-4 cursor-pointer hover:bg-slate-50/50 transition"
        onClick={onToggle}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div className={`shrink-0 px-2 py-1 rounded-lg text-xs font-medium ${meta.color}`}>
              {meta.icon} {meta.label}
            </div>
            <span className="text-xs text-slate-500">{entry.user_id_masked || "..."}</span>
            <span className="text-xs text-slate-400">{time}</span>
          </div>
          <div className="shrink-0 text-slate-400">
            {isExpanded ? <ChevronUpIcon className="w-5 h-5" /> : <ChevronDownIcon className="w-5 h-5" />}
          </div>
        </div>
        <div className="mt-2 flex items-start gap-2">
          <div className="shrink-0 w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
            <UserIcon className="w-4 h-4 text-blue-600" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-slate-700 line-clamp-2" dir="auto">
              {entry.user_message || "(no message)"}
            </p>
          </div>
          <ArrowRightIcon className="w-4 h-4 text-slate-300 shrink-0 mt-1" />
          <div className="shrink-0 w-8 h-8 rounded-full bg-violet-100 flex items-center justify-center">
            <ChatBubbleLeftRightIcon className="w-4 h-4 text-violet-600" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-slate-700 line-clamp-2" dir="auto">
              {entry.bot_to_user || "(no response)"}
            </p>
          </div>
        </div>
      </div>

      {isExpanded && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          className="border-t border-slate-100 bg-slate-50/50"
        >
          <div className="p-4 space-y-3 text-sm">
            {entry.ai_raw_response && (
              <div>
                <p className="font-medium text-slate-600 mb-1 flex items-center gap-2">
                  <CpuChipIcon className="w-4 h-4" /> AI Raw Response
                </p>
                <pre className="p-3 bg-white rounded-lg border border-slate-200 text-xs overflow-x-auto max-h-40 overflow-y-auto whitespace-pre-wrap" dir="auto">
                  {entry.ai_raw_response}
                </pre>
              </div>
            )}
            <div className="flex flex-wrap gap-4 text-slate-600">
              {entry.model && <span>Model: <code className="bg-white px-1 rounded">{entry.model}</code></span>}
              {entry.tokens != null && <span>Tokens: {entry.tokens}</span>}
              {entry.response_time_ms != null && <span>Response: {Math.round(entry.response_time_ms)}ms</span>}
              {entry.qa_match_score != null && <span>Q&A Match: {(entry.qa_match_score * 100).toFixed(0)}%</span>}
              {entry.tool_calls?.length > 0 && (
                <span>Tools: {entry.tool_calls.join(", ")}</span>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
};

const ActivityFlow = () => {
  const { getFlowLogs } = useApi();
  const [flows, setFlows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [limit, setLimit] = useState(30);

  const fetchFlows = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getFlowLogs(limit);
      if (res.success && res.data) {
        setFlows(res.data.slice().reverse());
      } else {
        setFlows([]);
      }
    } catch (e) {
      setFlows([]);
    } finally {
      setLoading(false);
    }
  }, [getFlowLogs, limit]);

  useEffect(() => {
    fetchFlows();
    const interval = setInterval(fetchFlows, 8000);
    return () => clearInterval(interval);
  }, [fetchFlows]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Activity Flow</h1>
        <p className="text-slate-600 mt-1">
          شوف شو عم يصير بين المستخدم، البوت، والـ AI — شو طلب المستخدم، شو بعت البوت للـ AI، شو رجع الـ AI، وشو بعت البوت للمستخدم.
        </p>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <label className="text-sm text-slate-600">عرض:</label>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm"
          >
            <option value={15}>15</option>
            <option value={30}>30</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
        </div>
        <button
          onClick={fetchFlows}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 disabled:opacity-50 transition"
        >
          <ArrowPathIcon className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          تحديث
        </button>
      </div>

      <div className="flex items-center gap-4 p-4 bg-slate-50 rounded-xl border border-slate-200">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
            <UserIcon className="w-4 h-4 text-blue-600" />
          </div>
          <span className="text-sm font-medium text-slate-700">المستخدم</span>
        </div>
        <ArrowRightIcon className="w-5 h-5 text-slate-400" />
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center">
            <ChatBubbleLeftRightIcon className="w-4 h-4 text-slate-600" />
          </div>
          <span className="text-sm font-medium text-slate-700">البوت</span>
        </div>
        <ArrowRightIcon className="w-5 h-5 text-slate-400" />
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-violet-100 flex items-center justify-center">
            <CpuChipIcon className="w-4 h-4 text-violet-600" />
          </div>
          <span className="text-sm font-medium text-slate-700">الـ AI</span>
        </div>
        <ArrowRightIcon className="w-5 h-5 text-slate-400" />
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center">
            <ChatBubbleLeftRightIcon className="w-4 h-4 text-slate-600" />
          </div>
          <span className="text-sm font-medium text-slate-700">البوت</span>
        </div>
        <ArrowRightIcon className="w-5 h-5 text-slate-400" />
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
            <UserIcon className="w-4 h-4 text-blue-600" />
          </div>
          <span className="text-sm font-medium text-slate-700">المستخدم</span>
        </div>
      </div>

      {loading && flows.length === 0 ? (
        <div className="card p-12 text-center text-slate-500">
          <ArrowPathIcon className="w-12 h-12 mx-auto animate-spin text-primary-500 mb-4" />
          <p>جاري تحميل التدفق...</p>
        </div>
      ) : flows.length === 0 ? (
        <div className="card p-12 text-center text-slate-500">
          <ChatBubbleLeftRightIcon className="w-16 h-16 mx-auto opacity-50 mb-4" />
          <p>ما في تفاعلات جديدة. التفاعلات رح تظهر هون لما يرسل المستخدمين رسائل.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {flows.map((entry, idx) => (
            <FlowCard
              key={`${entry.timestamp}-${idx}`}
              entry={entry}
              isExpanded={expandedId === idx}
              onToggle={() => setExpandedId(expandedId === idx ? null : idx)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default ActivityFlow;
