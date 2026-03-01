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
  ListBulletIcon,
  MagnifyingGlassIcon,
} from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";

const SOURCE_LABELS = {
  gpt: { label: "GPT", color: "bg-violet-100 text-violet-700", icon: "🤖" },
  qa_database: { label: "Q&A DB", color: "bg-emerald-100 text-emerald-700", icon: "📚" },
  dynamic_retrieval: { label: "Dynamic", color: "bg-amber-100 text-amber-700", icon: "📂" },
  rate_limit: { label: "Rate Limit", color: "bg-orange-100 text-orange-700", icon: "⏱" },
  moderation: { label: "Moderation", color: "bg-rose-100 text-rose-700", icon: "🛡" },
};

/** Step block for the flow breakdown - supports long content with scroll */
const FlowStep = ({ step, title, content }) => {
  const str = typeof content === "string" ? content : String(content ?? "");
  const isJsonLike = str.trim().startsWith("{") || str.trim().startsWith("[");
  return (
    <div className="flex gap-3">
      <div className="shrink-0 w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center text-slate-600 font-semibold text-sm">
        {step}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">{title}</p>
        <div
          className="p-3 bg-white rounded-lg border border-slate-200 text-sm text-slate-700 max-h-48 overflow-y-auto overflow-x-auto"
          dir="auto"
        >
          {isJsonLike ? (
            <pre className="text-xs whitespace-pre-wrap m-0 font-mono">{str}</pre>
          ) : (
            <pre className="text-sm whitespace-pre-wrap m-0 font-sans">{str}</pre>
          )}
        </div>
      </div>
    </div>
  );
};

const FlowCard = ({ entry, isExpanded, onToggle }) => {
  const meta = SOURCE_LABELS[entry.source] || { label: entry.source, color: "bg-slate-100 text-slate-700", icon: "?" };
  const time = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";

  const isGptFlow = entry.source === "gpt";
  const hasAiDetails = isGptFlow && (entry.ai_query_summary || entry.ai_raw_response || entry.tool_calls?.length);

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
            <span className="text-xs font-medium text-slate-700">{entry.user_name || "—"}</span>
            <span className="text-xs text-slate-500">{entry.user_phone_masked ?? entry.user_id_masked ?? "..."}</span>
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
          <div className="p-4 space-y-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide flex items-center gap-2">
              <ListBulletIcon className="w-4 h-4" /> {entry.flow_steps?.length ? "Step-by-step flow" : "Detailed interaction flow (English)"}
            </p>

            {entry.flow_steps?.length > 0 ? (
              <div className="grid gap-4">
                {entry.flow_steps.map((s) => (
                  <FlowStep
                    key={s.step}
                    step={s.step}
                    title={s.title}
                    content={typeof s.content === "string" ? s.content : String(s.content ?? "")}
                  />
                ))}
              </div>
            ) : (
              <div className="grid gap-4">
                <FlowStep step={1} title="User sent to Bot" content={entry.user_message || "(no message)"} />
                <FlowStep
                  step={2}
                  title="Bot sent to AI"
                  content={
                    entry.ai_query_summary ||
                    (entry.source === "qa_database"
                      ? "Bot matched from Q&A database (no AI call)."
                      : entry.source === "dynamic_retrieval"
                      ? "Bot used dynamic retrieval (no GPT call)."
                      : entry.source === "rate_limit"
                      ? "Rate limit applied (no AI call)."
                      : entry.source === "moderation"
                      ? "Content moderated (no AI call)."
                      : "User query + context messages.")
                  }
                />
                {isGptFlow && (
                  <FlowStep
                    step={3}
                    title="AI processed"
                    content={
                      <span>
                        {entry.model && <span>Model: <code className="bg-slate-100 px-1 rounded">{entry.model}</code> </span>}
                        {entry.tokens != null && <span>• Tokens: {entry.tokens} </span>}
                        {entry.response_time_ms != null && <span>• Response time: {Math.round(entry.response_time_ms)}ms </span>}
                        {entry.qa_match_score != null && <span>• Q&A match: {(entry.qa_match_score * 100).toFixed(0)}% </span>}
                        {entry.tool_calls?.length > 0 && (
                          <span>• AI requested tools: <code className="bg-violet-100 px-1 rounded">{entry.tool_calls.join(", ")}</code></span>
                        )}
                        {!entry.model && !entry.tokens && !entry.tool_calls?.length && "(No metadata)"}
                      </span>
                    }
                  />
                )}
                {isGptFlow && entry.ai_raw_response && (
                  <FlowStep
                    step={4}
                    title="AI returned to Bot"
                    content={
                      <pre className="text-xs overflow-x-auto max-h-40 overflow-y-auto whitespace-pre-wrap m-0" dir="auto">
                        {entry.ai_raw_response}
                      </pre>
                    }
                  />
                )}
                <FlowStep
                  step={isGptFlow && entry.ai_raw_response ? 5 : (isGptFlow ? 4 : 3)}
                  title="Bot sent to User"
                  content={entry.bot_to_user || "(no response)"}
                />
              </div>
            )}

            {(entry.source === "gpt" || entry.source === "dynamic_retrieval") && (entry.tokens != null || entry.prompt_tokens != null || entry.completion_tokens != null || entry.model) && (
              <div className="mt-4 pt-4 border-t border-slate-200">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">GPT usage</p>
                <div className="p-3 bg-violet-50 rounded-lg border border-violet-100 text-sm text-slate-700 space-y-1">
                  {entry.model && <p>Model: <code className="bg-violet-100 px-1 rounded">{entry.model}</code></p>}
                  {entry.prompt_tokens != null && <p>Prompt tokens: <strong>{entry.prompt_tokens}</strong></p>}
                  {entry.completion_tokens != null && <p>Completion tokens: <strong>{entry.completion_tokens}</strong></p>}
                  {entry.tokens != null && <p>Total tokens: <strong>{entry.tokens}</strong></p>}
                  {entry.response_time_ms != null && <p>Response time: <strong>{Math.round(entry.response_time_ms)}ms</strong></p>}
                </div>
              </div>
            )}
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
  const [searchPhone, setSearchPhone] = useState("");

  const fetchFlows = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getFlowLogs(limit, searchPhone);
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
  }, [getFlowLogs, limit, searchPhone]);

  useEffect(() => {
    fetchFlows();
    const interval = setInterval(fetchFlows, 8000);
    return () => clearInterval(interval);
  }, [fetchFlows]);

  // Refetch when search changes (debounced)
  useEffect(() => {
    const t = setTimeout(fetchFlows, 400);
    return () => clearTimeout(t);
  }, [searchPhone, fetchFlows]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Activity Flow</h1>
        <p className="text-slate-600 mt-1">
          See what happens between the user, bot, and AI — what the user asked, what the bot sent to the AI, what the AI returned, and what the bot sent to the user.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <MagnifyingGlassIcon className="w-5 h-5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by phone..."
              value={searchPhone}
              onChange={(e) => setSearchPhone(e.target.value)}
              className="px-3 py-1.5 border border-slate-200 rounded-lg text-sm w-40"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-slate-600">Show:</label>
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
        </div>
        <button
          onClick={fetchFlows}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 disabled:opacity-50 transition"
        >
          <ArrowPathIcon className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Interaction flow</p>
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
              <UserIcon className="w-4 h-4 text-blue-600" />
            </div>
            <span className="text-sm font-medium text-slate-700">User</span>
          </div>
          <ArrowRightIcon className="w-5 h-5 text-slate-400" />
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center">
              <ChatBubbleLeftRightIcon className="w-4 h-4 text-slate-600" />
            </div>
            <span className="text-sm font-medium text-slate-700">Bot</span>
          </div>
          <ArrowRightIcon className="w-5 h-5 text-slate-400" />
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-violet-100 flex items-center justify-center">
              <CpuChipIcon className="w-4 h-4 text-violet-600" />
            </div>
            <span className="text-sm font-medium text-slate-700">AI</span>
          </div>
          <ArrowRightIcon className="w-5 h-5 text-slate-400" />
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center">
              <ChatBubbleLeftRightIcon className="w-4 h-4 text-slate-600" />
            </div>
            <span className="text-sm font-medium text-slate-700">Bot</span>
          </div>
          <ArrowRightIcon className="w-5 h-5 text-slate-400" />
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
              <UserIcon className="w-4 h-4 text-blue-600" />
            </div>
            <span className="text-sm font-medium text-slate-700">User</span>
          </div>
        </div>
        <p className="text-xs text-slate-500">
          User sends → Bot forwards to AI → AI processes (may request tools) → Bot executes and relays → User receives reply
        </p>
      </div>

      {loading && flows.length === 0 ? (
        <div className="card p-12 text-center text-slate-500">
          <ArrowPathIcon className="w-12 h-12 mx-auto animate-spin text-primary-500 mb-4" />
          <p>Loading flow...</p>
        </div>
      ) : flows.length === 0 ? (
        <div className="card p-12 text-center text-slate-500">
          <ChatBubbleLeftRightIcon className="w-16 h-16 mx-auto opacity-50 mb-4" />
          <p>No new interactions. Interactions will appear here when users send messages.</p>
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
