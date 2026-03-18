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

const MESSAGE_TYPE_LABELS = {
  text: { label: "Text", color: "bg-slate-100 text-slate-600", icon: "💬" },
  voice: { label: "Voice", color: "bg-blue-100 text-blue-700", icon: "🎤" },
  image: { label: "Image", color: "bg-pink-100 text-pink-700", icon: "🖼" },
};

const GENDER_META = {
  male: { label: "Male", color: "bg-sky-100 text-sky-700" },
  female: { label: "Female", color: "bg-pink-100 text-pink-700" },
  unknown: { label: "Gender: Unknown", color: "bg-slate-100 text-slate-600" },
};

const FILE_STATUS_META = {
  existing_file: { label: "Has File", color: "bg-emerald-100 text-emerald-700" },
  new_customer: { label: "New Customer", color: "bg-amber-100 text-amber-700" },
  unknown: { label: "File Status: Unknown", color: "bg-slate-100 text-slate-600" },
};

/** Step block for the flow breakdown - supports long content with scroll */
const FlowStep = ({ step, title, content, tokens, isMaxTokens, model, costUsd, eventType, status, durationMs, metadata }) => {
  const str = typeof content === "string" ? content : String(content ?? "");
  const isJsonLike = str.trim().startsWith("{") || str.trim().startsWith("[");
  const isLong = str.length > 800;
  const isError = title && String(title).includes("❌");
  const isSummary = title && String(title).includes("Summary");
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="flex gap-3">
      <div className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center font-semibold text-sm ${isError ? "bg-red-100 text-red-700" : isSummary ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
        {step}
      </div>
      <div className="flex-1 min-w-0">
        <p className={`text-xs font-semibold uppercase tracking-wide mb-1 flex items-center gap-2 flex-wrap ${isError ? "text-red-600" : "text-slate-500"}`}>
          {title}
          {eventType && (
            <span className="text-[10px] font-normal normal-case bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">{eventType}</span>
          )}
          {status && (
            <span className={`text-[10px] font-normal normal-case px-1.5 py-0.5 rounded ${status === "success" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{status}</span>
          )}
          {durationMs != null && (
            <span className="text-[10px] font-normal normal-case text-slate-500">{durationMs}ms</span>
          )}
          {tokens != null && (
            <span className={`text-xs font-normal normal-case ${isMaxTokens ? "bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded" : "text-slate-500"}`}>
              {tokens.toLocaleString()} tokens {isMaxTokens && "↑ الأكثر"}
            </span>
          )}
          {model && (
            <span className="text-xs font-normal normal-case bg-violet-100 text-violet-700 px-1.5 py-0.5 rounded">{model}</span>
          )}
          {costUsd != null && (
            <span className="text-xs font-normal normal-case text-emerald-700 font-medium">${Number(costUsd).toFixed(6)}</span>
          )}
        </p>
        <div
          className={`p-3 rounded-lg border text-sm overflow-y-auto overflow-x-auto ${
            isError ? "bg-red-50 border-red-200 text-red-800" : "bg-white border-slate-200 text-slate-700"
          } ${expanded || !isLong ? "max-h-[32rem]" : "max-h-48"}`}
          dir="auto"
        >
          {isJsonLike ? (
            <pre className="text-xs whitespace-pre-wrap m-0 font-mono">{str}</pre>
          ) : (
            <pre className="text-sm whitespace-pre-wrap m-0 font-sans">{str}</pre>
          )}
        </div>
        {metadata && Object.keys(metadata).length > 0 && (
          <div className="mt-2 pt-2 border-t border-slate-100">
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">Metadata</p>
            <pre className="text-[10px] text-slate-600 whitespace-pre-wrap m-0 font-mono">{JSON.stringify(metadata, null, 2)}</pre>
          </div>
        )}
        {isLong && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-1 text-xs text-blue-600 hover:text-blue-700 font-medium"
          >
            {expanded ? "Show less" : "Show full content"}
          </button>
        )}
      </div>
    </div>
  );
};

const FlowCard = ({ entry, isExpanded, onToggle }) => {
  const meta = SOURCE_LABELS[entry.source] || { label: entry.source, color: "bg-slate-100 text-slate-700", icon: "?" };
  const msgTypeMeta = MESSAGE_TYPE_LABELS[entry.message_type] || MESSAGE_TYPE_LABELS.text;
  const time = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
  const genderKey = (entry.user_gender || "unknown").toLowerCase();
  const genderMeta = GENDER_META[genderKey] || GENDER_META.unknown;
  const fileStatusKey = (entry.customer_file_status || "unknown").toLowerCase();
  const fileStatusMeta = FILE_STATUS_META[fileStatusKey] || FILE_STATUS_META.unknown;
  const displayName = entry.user_name || "Unknown";
  const displayPhone = entry.user_phone || entry.user_phone_masked || entry.user_id || entry.user_id_masked || "...";

  const isGptFlow = entry.source === "gpt";
  const hasAiDetails = isGptFlow && (entry.ai_query_summary || entry.ai_raw_response || entry.tool_calls?.length);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="card"
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
            <div className={`shrink-0 px-2 py-1 rounded-lg text-xs font-medium ${msgTypeMeta.color}`}>
              {msgTypeMeta.icon} {msgTypeMeta.label}
            </div>
            <span className="text-xs font-semibold text-slate-700">{displayName}</span>
            <span className="text-xs text-slate-500">{displayPhone}</span>
            <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${genderMeta.color}`}>{genderMeta.label}</span>
            <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${fileStatusMeta.color}`}>{fileStatusMeta.label}</span>
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
            {entry.flow_error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-xs font-semibold text-red-700 uppercase tracking-wide mb-1">❌ Error</p>
                <pre className="text-sm text-red-800 whitespace-pre-wrap m-0 font-sans" dir="auto">{entry.flow_error}</pre>
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="p-3 bg-white rounded-lg border border-slate-200 text-sm">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">User Info</p>
                <p className="text-slate-700"><strong>Name:</strong> {displayName}</p>
                <p className="text-slate-700"><strong>Phone:</strong> {displayPhone}</p>
              </div>
              <div className="p-3 bg-white rounded-lg border border-slate-200 text-sm">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Customer Status</p>
                <p className="text-slate-700"><strong>Gender:</strong> {genderMeta.label.replace("Gender: ", "")}</p>
                <p className="text-slate-700"><strong>File:</strong> {fileStatusMeta.label.replace("File Status: ", "")}</p>
              </div>
            </div>

            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide flex items-center gap-2">
              <ListBulletIcon className="w-4 h-4" /> {entry.flow_steps?.length ? "Step-by-step flow" : "Detailed interaction flow (English)"}
            </p>

            {entry.flow_steps?.length > 0 ? (
              <div className="max-h-[70vh] overflow-y-auto overflow-x-hidden pr-1 -mr-1">
                <div className="grid gap-4">
                  {(() => {
                    const maxT = Math.max(0, ...(entry.flow_steps || []).map((s) => (s.tokens != null ? s.tokens : 0)));
                    return (entry.flow_steps || []).map((s) => (
                      <FlowStep
                        key={s.step}
                        step={s.step}
                        title={s.title}
                        content={typeof s.content === "string" ? s.content : String(s.content ?? "")}
                        tokens={s.tokens}
                        isMaxTokens={s.tokens != null && s.tokens > 0 && s.tokens === maxT}
                        model={s.model}
                        costUsd={s.cost_usd}
                        eventType={s.event_type}
                        status={s.status}
                        durationMs={s.duration_ms}
                        metadata={s.metadata}
                      />
                    ));
                  })()}
                </div>
              </div>
            ) : (
              <div className="grid gap-4">
                <FlowStep step={1} title="User sent to Bot" content={entry.user_message || "(no message)"} />
                <FlowStep
                  step={2}
                  title="Bot sent to AI"
                  content={
                    entry.bot_sent_to_ai_full ||
                    entry.ai_query_summary ||
                    (String(entry.source || "").startsWith("router_")
                      ? `No AI call. Decision made by code-level router.\nSource: ${entry.source}`
                      : null) ||
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
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">GPT usage – كل التوكينات</p>
                  {(entry.token_source || entry.prompt_tokens != null) && (
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${(entry.token_source || "backend") === "backend" ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700"}`}>
                      {(entry.token_source || "backend") === "backend" ? "Backend (GPT API)" : (entry.token_source || "Backend (GPT API)")}
                    </span>
                  )}
                </div>
                <div className="p-3 bg-violet-50 rounded-lg border border-violet-100 text-sm text-slate-700 space-y-1">
                  {entry.model && <p>Model: <code className="bg-violet-100 px-1 rounded">{entry.model}</code></p>}
                  {entry.prompt_tokens != null && <p>Input tokens: <strong>{entry.prompt_tokens.toLocaleString()}</strong>{entry.input_cost_usd != null && <span className="text-emerald-600 ml-1">(${entry.input_cost_usd.toFixed(6)})</span>}</p>}
                  {entry.completion_tokens != null && <p>Output tokens: <strong>{entry.completion_tokens.toLocaleString()}</strong>{entry.output_cost_usd != null && <span className="text-emerald-600 ml-1">(${entry.output_cost_usd.toFixed(6)})</span>}</p>}
                  {entry.tokens != null && <p>Total tokens: <strong>{entry.tokens.toLocaleString()}</strong></p>}
                  {entry.cost_usd != null && <p className="font-semibold text-emerald-700">Total cost: <strong>${entry.cost_usd.toFixed(6)}</strong></p>}
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

/** Stable key per entry so auto-refresh doesn't collapse the expanded card */
const getEntryKey = (entry) =>
  [entry.timestamp, entry.user_id || "", entry.user_phone || ""].filter(Boolean).join("|");

const ActivityFlow = () => {
  const { getFlowLogs } = useApi();
  const [flows, setFlows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedKey, setExpandedKey] = useState(null);
  const [limit, setLimit] = useState(15);
  const [searchPhone, setSearchPhone] = useState("");

  const fetchFlows = useCallback(async (isRefresh = false) => {
    try {
      if (!isRefresh) setLoading(true);
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

  const fetchFlowsRef = React.useRef(fetchFlows);
  fetchFlowsRef.current = fetchFlows;

  // Initial load only; no auto-refresh (user can click Refresh)
  useEffect(() => {
    fetchFlowsRef.current?.(false);
  }, []);

  // Refetch when search or limit changes (debounced); skip on initial mount
  const didMount = React.useRef(false);
  useEffect(() => {
    if (!didMount.current) {
      didMount.current = true;
      return;
    }
    const t = setTimeout(() => fetchFlowsRef.current?.(false), 400);
    return () => clearTimeout(t);
  }, [searchPhone, limit]);

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
          onClick={() => fetchFlows(false)}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 disabled:opacity-50 transition"
        >
          <ArrowPathIcon className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          {loading && flows.length > 0 ? "Updating…" : "Refresh"}
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
          {flows.map((entry) => {
            const key = getEntryKey(entry);
            return (
              <FlowCard
                key={key}
                entry={entry}
                isExpanded={expandedKey === key}
                onToggle={() => setExpandedKey(expandedKey === key ? null : key)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ActivityFlow;
