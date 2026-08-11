import { useState, useEffect, useCallback, useRef } from "react";
import {
  ArrowPathIcon,
  UserIcon,
  ChatBubbleLeftRightIcon,
  CpuChipIcon,
  ArrowRightIcon,
  MagnifyingGlassIcon,
} from "@heroicons/react/24/outline";
import { useApi } from "../hooks/useApi";
import { getEntryKey } from "./ActivityFlow.meta";
import { FlowCard } from "./ActivityFlowCard";

const ActivityFlow = () => {
  const { getFlowLogs } = useApi();
  const [flows, setFlows] = useState(/** @type {ActivityFlowEntry[]} */ ([]));
  const [loading, setLoading] = useState(true);
  const [expandedKey, setExpandedKey] = useState(/** @type {string | null} */ (null));
  const [limit, setLimit] = useState(15);
  const [searchPhone, setSearchPhone] = useState("");

  const fetchFlows = useCallback(async (isRefresh = false) => {
    try {
      if (!isRefresh) setLoading(true);
      const res = await getFlowLogs(limit, searchPhone);
      if (res.success && res.data) {
        setFlows(/** @type {ActivityFlowEntry[]} */ (Array.isArray(res.data) ? res.data.slice().reverse() : []));
      } else {
        setFlows([]);
      }
    } catch {
      setFlows([]);
    } finally {
      setLoading(false);
    }
  }, [getFlowLogs, limit, searchPhone]);

  const fetchFlowsRef = useRef(fetchFlows);
  fetchFlowsRef.current = fetchFlows;

  // Initial load only; no auto-refresh (user can click Refresh)
  useEffect(() => {
    fetchFlowsRef.current?.(false);
  }, []);

  // Refetch when search or limit changes (debounced); skip on initial mount
  const didMount = useRef(false);
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
        <h1 className="text-2xl font-bold text-slate-800">Interaction Logs</h1>
        <p className="text-sm text-slate-500 mt-1">Read-only observability of user ↔ bot ↔ AI turns (not a workflow engine).</p>
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
        <div
          className="overflow-x-auto overflow-y-hidden pb-2 -mx-1 px-1 touch-pan-x overscroll-x-contain [scrollbar-width:thin]"
          style={{ WebkitOverflowScrolling: "touch" }}
        >
          <div className="flex items-center gap-4 flex-nowrap min-w-max">
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
