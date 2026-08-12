import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import {
  UserIcon,
  ChatBubbleLeftRightIcon,
  ArrowRightIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ListBulletIcon,
} from "@heroicons/react/24/outline";
import {
  DEFAULT_MSG_TYPE,
  DEFAULT_GENDER_META,
  DEFAULT_FILE_STATUS_META,
  SOURCE_LABELS,
  CHANNEL_LABELS,
  MESSAGE_TYPE_LABELS,
  GENDER_META,
  FILE_STATUS_META,
  formatUsd,
  costSummary,
} from "./ActivityFlow.meta";
import { redactActivityFlowEntryForJson } from "./ActivityFlow.redact";
import { FlowStep } from "./ActivityFlowStep";

/**
 * @param {{ entry: ActivityFlowEntry, isExpanded: boolean, onToggle: () => void }} props
 */
export const FlowCard = ({ entry, isExpanded, onToggle }) => {
  const cardRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  useEffect(() => {
    if (!isExpanded) return;
    const t = setTimeout(() => {
      cardRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
        inline: "nearest",
      });
    }, 120);
    return () => clearTimeout(t);
  }, [isExpanded]);

  const sourceKey = typeof entry.source === "string" ? entry.source : "";
  const messageTypeKey = typeof entry.message_type === "string" ? entry.message_type : "text";
  const meta = SOURCE_LABELS[sourceKey] || { label: String(entry.source ?? ""), color: "bg-slate-100 text-slate-700", icon: "?" };
  const msgTypeMeta = MESSAGE_TYPE_LABELS[messageTypeKey] ?? MESSAGE_TYPE_LABELS.text ?? DEFAULT_MSG_TYPE;
  const time = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
  const genderKey = (entry.user_gender || "unknown").toLowerCase();
  const genderMeta = GENDER_META[genderKey] ?? GENDER_META.unknown ?? DEFAULT_GENDER_META;
  const fileStatusKey = (entry.customer_file_status || "unknown").toLowerCase();
  const fileStatusMeta = FILE_STATUS_META[fileStatusKey] ?? FILE_STATUS_META.unknown ?? DEFAULT_FILE_STATUS_META;
  const displayName = entry.user_name || "Unknown";
  const displayPhone = entry.user_phone || entry.user_phone_masked || entry.user_id || entry.user_id_masked || "...";

  const isGptFlow = entry.source === "gpt";
  const channelKey = (entry.channel || "unknown").toLowerCase();
  const channelMeta = CHANNEL_LABELS[channelKey] ?? CHANNEL_LABELS.unknown;
  const costMeta = costSummary(entry);
  const cm = entry.cm_diagnostics;
  const faq = entry.faq_match;
  const [showRawJson, setShowRawJson] = useState(false);
  return (
    <div ref={cardRef} className="scroll-mt-24">
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
          <div className="flex items-center gap-3 min-w-0 flex-1 flex-wrap">
            <div className={`shrink-0 px-2 py-1 rounded-lg text-xs font-medium ${meta.color}`}>
              {meta.icon} {meta.label}
            </div>
            <div className={`shrink-0 px-2 py-1 rounded-lg text-xs font-medium ${channelMeta?.color || "bg-slate-100 text-slate-600"}`}>
              {channelMeta?.label || "Unknown"}
            </div>
            <div className={`shrink-0 px-2 py-1 rounded-lg text-xs font-medium ${msgTypeMeta.color}`}>
              {msgTypeMeta.icon} {msgTypeMeta.label}
            </div>
            <span className={`shrink-0 px-2 py-1 rounded-lg text-xs font-semibold ${costMeta.tone}`} title={costMeta.detail || undefined}>
              {costMeta.label}
              {costMeta.detail ? <span className="font-normal opacity-80 ml-1">({costMeta.detail})</span> : null}
            </span>
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

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
              <div className="p-3 bg-white rounded-lg border border-slate-200 text-sm">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Where it went</p>
                <p className="text-slate-700"><strong>Channel:</strong> {channelMeta?.label || entry.channel || "Unknown"}</p>
                <p className="text-slate-700"><strong>Direction:</strong> {entry.direction || "inbound"}</p>
                <p className="text-slate-700"><strong>Handler:</strong> {entry.handler_path || entry.source || "—"}</p>
                <p className="text-slate-700 break-all"><strong>Conversation:</strong> {entry.conversation_id || "—"}</p>
              </div>
              <div className="p-3 bg-white rounded-lg border border-slate-200 text-sm">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">What happened</p>
                <p className="text-slate-700"><strong>Outcome:</strong> {entry.outcome || entry.source || "—"}</p>
                <p className="text-slate-700"><strong>Source:</strong> {meta.label}</p>
                {faq ? (
                  <p className="text-slate-700">
                    <strong>FAQ:</strong> id={String(faq.faq_id ?? "—")} · {faq.tier || "match"}
                    {faq.similarity != null ? ` · ${(Number(faq.similarity) * 100).toFixed(0)}%` : ""}
                  </p>
                ) : null}
                {Array.isArray(entry.pipeline_decisions) && entry.pipeline_decisions.length > 0 ? (
                  <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
                    {entry.pipeline_decisions.slice(0, 8).map((d, i) => (
                      <li key={`${String(d.step)}-${i}`}>
                        {String(d.step || "step")}: {String(d.decision ?? JSON.stringify(d))}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
              <div className="p-3 bg-white rounded-lg border border-slate-200 text-sm">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">What it read</p>
                {cm ? (
                  <>
                    <p className="text-slate-700"><strong>CM reason:</strong> {cm.reason || "—"}</p>
                    <p className="text-slate-700 break-all"><strong>Content ver:</strong> {cm.content_version_id || "—"}</p>
                    <p className="text-slate-700"><strong>Sources:</strong> {(cm.source_ids || []).length}</p>
                    {(cm.retrieved_sources || []).slice(0, 5).map((s) => (
                      <p key={String(s.source_id)} className="text-xs text-slate-600 truncate" title={s.title || s.source_id}>
                        · {s.source_id}{s.title ? ` — ${s.title}` : ""}
                      </p>
                    ))}
                    {(cm.retrieved_sources || []).length > 5 ? (
                      <p className="text-xs text-slate-400">+{(cm.retrieved_sources || []).length - 5} more</p>
                    ) : null}
                  </>
                ) : (
                  <p className="text-slate-500 text-xs">No CM retrieval diagnostics for this turn.</p>
                )}
              </div>
              <div className="p-3 bg-white rounded-lg border border-slate-200 text-sm">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Cost & tokens</p>
                {entry.cost_status === "none" ? (
                  <p className="text-slate-600">No AI call — cost N/A</p>
                ) : entry.cost_usd != null ? (
                  <>
                    <p className="font-semibold text-emerald-700">{formatUsd(entry.cost_usd)}</p>
                    <p className="text-xs text-slate-500">Status: {entry.cost_status || "estimated"}</p>
                    {entry.cost_basis ? <p className="text-[10px] text-slate-400 break-all">{entry.cost_basis}</p> : null}
                  </>
                ) : (
                  <p className="text-amber-700 font-medium">unavailable</p>
                )}
                {entry.model ? <p className="text-slate-700 mt-1"><strong>Model:</strong> <code className="bg-slate-100 px-1 rounded">{entry.model}</code></p> : null}
                {entry.prompt_tokens != null ? <p className="text-slate-700">In: {entry.prompt_tokens.toLocaleString()}{entry.input_cost_usd != null ? ` (${formatUsd(entry.input_cost_usd)})` : ""}</p> : null}
                {entry.completion_tokens != null ? <p className="text-slate-700">Out: {entry.completion_tokens.toLocaleString()}{entry.output_cost_usd != null ? ` (${formatUsd(entry.output_cost_usd)})` : ""}</p> : null}
                {entry.tokens != null ? <p className="text-slate-700">Total tokens: {entry.tokens.toLocaleString()}</p> : null}
              </div>
            </div>

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

            {entry.flow_steps && entry.flow_steps.length > 0 ? (
              <div className="overflow-x-auto overflow-y-visible touch-pan-x">
                <div className="grid gap-4 min-w-0">
                  {(() => {
                    const steps = entry.flow_steps ?? [];
                    const maxT = Math.max(0, ...steps.map((/** @type {FlowStepData} */ s) => (s.tokens != null ? s.tokens : 0)));
                    return steps.map((/** @type {FlowStepData} */ s) => (
                      <FlowStep
                        key={s.step ?? 0}
                        step={s.step ?? 0}
                        title={s.title ?? ""}
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
                {entry.customer_context_sent && (
                  <FlowStep
                    step={2}
                    title="Bot → AI (Customer context)"
                    content={entry.customer_context_sent}
                  />
                )}
                <FlowStep
                  step={entry.customer_context_sent ? 3 : 2}
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
                    step={entry.customer_context_sent ? 4 : 3}
                    title="AI processed"
                    content={
                      <span>
                        {entry.model && <span>Model: <code className="bg-slate-100 px-1 rounded">{entry.model}</code> </span>}
                        {entry.tokens != null && <span>• Tokens: {entry.tokens} </span>}
                        {entry.response_time_ms != null && <span>• Response time: {Math.round(entry.response_time_ms)}ms </span>}
                        {entry.qa_match_score != null && <span>• Q&A match: {(entry.qa_match_score * 100).toFixed(0)}% </span>}
                        {entry.tool_calls && entry.tool_calls.length > 0 && (
                          <span>• AI requested tools: <code className="bg-violet-100 px-1 rounded">{entry.tool_calls.join(", ")}</code></span>
                        )}
                        {!entry.model && !entry.tokens && !(entry.tool_calls && entry.tool_calls.length > 0) && "(No metadata)"}
                      </span>
                    }
                  />
                )}
                {isGptFlow && entry.ai_raw_response && (
                  <FlowStep
                    step={entry.customer_context_sent ? 5 : 4}
                    title="AI returned to Bot"
                    content={
                      <pre className="text-xs overflow-x-auto max-h-40 overflow-y-auto whitespace-pre-wrap m-0" dir="auto">
                        {entry.ai_raw_response}
                      </pre>
                    }
                  />
                )}
                <FlowStep
                  step={
                    entry.customer_context_sent
                      ? (isGptFlow && entry.ai_raw_response ? 6 : isGptFlow ? 5 : 4)
                      : (isGptFlow && entry.ai_raw_response ? 5 : isGptFlow ? 4 : 3)
                  }
                  title="Bot sent to User"
                  content={entry.bot_to_user || "(no response)"}
                />
              </div>
            )}

            {(entry.source === "gpt" || entry.source === "dynamic_retrieval" || entry.cost_usd != null || entry.prompt_tokens != null) && (
              <div className="mt-4 pt-4 border-t border-slate-200">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">GPT usage — tokens & cost</p>
                  {(entry.token_source || entry.prompt_tokens != null) && (
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${(entry.token_source || "backend") === "backend" ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700"}`}>
                      {(entry.token_source || "backend") === "backend" ? "Backend (GPT API)" : (entry.token_source || "Backend (GPT API)")}
                    </span>
                  )}
                </div>
                <div className="p-3 bg-violet-50 rounded-lg border border-violet-100 text-sm text-slate-700 space-y-1">
                  {entry.model && <p>Model: <code className="bg-violet-100 px-1 rounded">{entry.model}</code></p>}
                  {entry.prompt_tokens != null && <p>Input tokens: <strong>{entry.prompt_tokens.toLocaleString()}</strong>{entry.input_cost_usd != null && <span className="text-emerald-600 ml-1">({formatUsd(entry.input_cost_usd)})</span>}</p>}
                  {entry.completion_tokens != null && <p>Output tokens: <strong>{entry.completion_tokens.toLocaleString()}</strong>{entry.output_cost_usd != null && <span className="text-emerald-600 ml-1">({formatUsd(entry.output_cost_usd)})</span>}</p>}
                  {entry.tokens != null && <p>Total tokens: <strong>{entry.tokens.toLocaleString()}</strong></p>}
                  {entry.cost_usd != null ? (
                    <p className="font-semibold text-emerald-700">Total cost: <strong>{formatUsd(entry.cost_usd)}</strong></p>
                  ) : entry.cost_status !== "none" ? (
                    <p className="font-semibold text-amber-700">Total cost: unavailable</p>
                  ) : null}
                  {entry.response_time_ms != null && <p>Response time: <strong>{Math.round(entry.response_time_ms)}ms</strong></p>}
                </div>
              </div>
            )}

            <div className="pt-2 border-t border-slate-200">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowRawJson((v) => !v);
                }}
                className="text-xs text-slate-500 hover:text-slate-700 font-medium"
              >
                {showRawJson ? "Hide technical JSON" : "Show technical JSON"}
              </button>
              {showRawJson ? (
                <pre className="mt-2 p-3 bg-slate-900 text-slate-100 text-[10px] rounded-lg overflow-auto max-h-72 whitespace-pre-wrap">
                  {JSON.stringify(redactActivityFlowEntryForJson(entry), null, 2)}
                </pre>
              ) : null}
            </div>
          </div>
        </motion.div>
      )}
    </motion.div>
    </div>
  );
};

