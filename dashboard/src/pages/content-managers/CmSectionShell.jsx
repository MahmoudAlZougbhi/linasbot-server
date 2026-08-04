import { Link } from "react-router-dom";
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/24/outline";

/**
 * Shared chrome for owner-facing CM section pages.
 * @param {{
 *   title: string;
 *   description: string;
 *   countLabel?: string;
 *   loading?: boolean;
 *   dirty?: boolean;
 *   saving?: boolean;
 *   validating?: boolean;
 *   conflict?: string | null;
 *   meta?: Record<string, unknown> | null;
 *   validation?: { ok?: boolean; errors?: Array<Record<string, unknown>>; warnings?: Array<Record<string, unknown>> } | null;
 *   onReload: () => void;
 *   onSave: () => void;
 *   onValidate: () => void;
 *   children: import('react').ReactNode;
 * }} props
 */
const CmSectionShell = ({
  title,
  description,
  countLabel,
  loading,
  dirty,
  saving,
  validating,
  conflict,
  meta,
  validation,
  onReload,
  onSave,
  onValidate,
  children,
}) => {
  const runtime = typeof meta?.runtime_mode === "string" ? meta.runtime_mode : "unknown";
  const publishEnabled = Boolean(meta?.publish_enabled);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Link to="/content-managers" className="inline-flex items-center text-sm text-slate-500 hover:text-slate-800 mb-2">
            <ArrowLeftIcon className="w-4 h-4 mr-1" /> Content Managers
          </Link>
          <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
          <p className="text-slate-600 mt-1 max-w-3xl">{description}</p>
          {countLabel ? <p className="text-sm text-slate-500 mt-2">{countLabel}</p> : null}
        </div>
        <div className="text-xs text-slate-500 space-y-1 text-right">
          <div>Runtime: {runtime}</div>
          <div>Publish: {publishEnabled ? "enabled" : "drafts only"}</div>
          {dirty ? <div className="text-amber-700 font-medium">Unsaved changes</div> : null}
          <Link to="/content-managers/publish" className="text-emerald-700 hover:underline block">
            Preview / Validate / Publish →
          </Link>
        </div>
      </div>

      {conflict ? (
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 flex gap-2">
          <ExclamationTriangleIcon className="w-5 h-5 shrink-0" />
          <div>
            <p className="font-medium">Version conflict</p>
            <p>{conflict}</p>
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onReload}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50"
        >
          <ArrowPathIcon className="w-4 h-4" /> Reload
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={saving || loading}
          className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save Draft"}
        </button>
        <button
          type="button"
          onClick={onValidate}
          disabled={validating || loading}
          className="inline-flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 disabled:opacity-50"
        >
          <CheckCircleIcon className="w-4 h-4" />
          {validating ? "Validating…" : "Validate"}
        </button>
      </div>

      {validation ? (
        <div
          className={`rounded-xl border px-4 py-3 text-sm ${
            validation.ok ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-rose-200 bg-rose-50 text-rose-900"
          }`}
        >
          {validation.ok
            ? "Validation OK — ready for publish review."
            : `${(validation.errors || []).length} validation error(s). Fix before publish.`}
        </div>
      ) : null}

      {loading ? <p className="text-sm text-slate-500">Loading…</p> : children}
    </div>
  );
};

export default CmSectionShell;
