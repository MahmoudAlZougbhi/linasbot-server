/** ActivityFlow label maps and cost helpers (LOC split). */

const DEFAULT_MSG_TYPE = { label: "Text", color: "bg-slate-100 text-slate-600", icon: "💬" };
const DEFAULT_GENDER_META = { label: "Gender: Unknown", color: "bg-slate-100 text-slate-600" };
const DEFAULT_FILE_STATUS_META = { label: "File Status: Unknown", color: "bg-slate-100 text-slate-600" };

/** @type {Record<string, { label: string; color: string; icon: string }>} */
const SOURCE_LABELS = {
  gpt: { label: "GPT", color: "bg-violet-100 text-violet-700", icon: "🤖" },
  qa_database: { label: "Q&A DB", color: "bg-emerald-100 text-emerald-700", icon: "📚" },
  dynamic_retrieval: { label: "Dynamic", color: "bg-amber-100 text-amber-700", icon: "📂" },
  rate_limit: { label: "Rate Limit", color: "bg-orange-100 text-orange-700", icon: "⏱" },
  moderation: { label: "Moderation", color: "bg-rose-100 text-rose-700", icon: "🛡" },
  out_of_scope_guard: { label: "Out of scope", color: "bg-rose-100 text-rose-700", icon: "🚫" },
  packet_ready: { label: "CM AI", color: "bg-cyan-100 text-cyan-700", icon: "📦" },
  answer_validation_failed: { label: "CM fail", color: "bg-rose-100 text-rose-700", icon: "📦" },
  cm_runtime: { label: "CM", color: "bg-cyan-100 text-cyan-700", icon: "📦" },
};

/** @type {Record<string, { label: string; color: string }>} */
const CHANNEL_LABELS = {
  whatsapp: { label: "WhatsApp", color: "bg-green-100 text-green-700" },
  instagram: { label: "Instagram", color: "bg-fuchsia-100 text-fuchsia-700" },
  facebook: { label: "Facebook", color: "bg-blue-100 text-blue-700" },
  testing_lab: { label: "Testing Lab", color: "bg-indigo-100 text-indigo-700" },
  unknown: { label: "Unknown", color: "bg-slate-100 text-slate-600" },
};

/** @param {number | null | undefined} n */
const formatUsd = (n) => {
  if (n == null || Number.isNaN(Number(n))) return null;
  const v = Number(n);
  if (v === 0) return "$0.0000";
  if (Math.abs(v) < 0.01) return `$${v.toFixed(4)}`;
  return `$${v.toFixed(4)}`;
};

/**
 * @param {ActivityFlowEntry} entry
 * @returns {{ label: string, detail: string | null, tone: string }}
 */
const costSummary = (entry) => {
  const status = String(entry.cost_status || "").toLowerCase();
  if (status === "none") {
    return { label: "No AI cost", detail: null, tone: "bg-slate-100 text-slate-600" };
  }
  if (entry.cost_usd != null) {
    return {
      label: formatUsd(entry.cost_usd) || "—",
      detail: status === "estimated" ? "est." : status || null,
      tone: "bg-emerald-50 text-emerald-700",
    };
  }
  return { label: "unavailable", detail: "historical or missing usage", tone: "bg-amber-50 text-amber-700" };
};

/** @type {Record<string, { label: string; color: string; icon: string }>} */
const MESSAGE_TYPE_LABELS = {
  text: { label: "Text", color: "bg-slate-100 text-slate-600", icon: "💬" },
  voice: { label: "Voice", color: "bg-blue-100 text-blue-700", icon: "🎤" },
  image: { label: "Image", color: "bg-pink-100 text-pink-700", icon: "🖼" },
};

/** @type {Record<string, { label: string; color: string }>} */
const GENDER_META = {
  male: { label: "Male", color: "bg-sky-100 text-sky-700" },
  female: { label: "Female", color: "bg-pink-100 text-pink-700" },
  unknown: { label: "Gender: Unknown", color: "bg-slate-100 text-slate-600" },
};

/** @type {Record<string, { label: string; color: string }>} */
const FILE_STATUS_META = {
  existing_file: { label: "Has File", color: "bg-emerald-100 text-emerald-700" },
  new_customer: { label: "New Customer", color: "bg-amber-100 text-amber-700" },
  unknown: { label: "File Status: Unknown", color: "bg-slate-100 text-slate-600" },
};

/** Stable key per entry so auto-refresh doesn't collapse the expanded card */
/** @param {ActivityFlowEntry} entry */
const getEntryKey = (entry) =>
  [entry.timestamp, entry.user_id || "", entry.user_phone || ""].filter(Boolean).join("|");

export {
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
  getEntryKey,
};
