import { useState } from "react";

/** Step block for the flow breakdown - supports long content with scroll */
/**
 * @param {{
 *   step: number,
 *   title: string,
 *   content: import('react').ReactNode,
 *   tokens?: number,
 *   isMaxTokens?: boolean,
 *   model?: string,
 *   costUsd?: number,
 *   eventType?: string,
 *   status?: string,
 *   durationMs?: number,
 *   metadata?: Record<string, unknown>,
 * }} props
 */
export const FlowStep = ({ step, title, content, tokens, isMaxTokens, model, costUsd, eventType, status, durationMs, metadata }) => {
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
              {tokens.toLocaleString()} tokens {isMaxTokens && "· max"}
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

