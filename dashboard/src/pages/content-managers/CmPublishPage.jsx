import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  LockClosedIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { useApi } from "../../hooks/useApi";

const DEFAULT_PUBLISH_MESSAGE =
  "Publishing is not enabled yet. This phase saves drafts only. No customer-facing AI behavior will change until a later approved phase.";

const CmPublishPage = () => {
  const {
    getCmMeta,
    validateCmDraft,
    publishCm,
    getCmVersions,
    buildCmPreviewPacket,
  } = useApi();

  const [meta, setMeta] = useState(
    /** @type {{ publish_enabled?: boolean; runtime_mode?: string; publish_disabled_message?: string | null } | null} */ (
      null
    )
  );
  const [versions, setVersions] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [validation, setValidation] = useState(
    /** @type {{ ok?: boolean; errors?: Array<Record<string, unknown>>; warnings?: Array<Record<string, unknown>> } | null} */ (
      null
    )
  );
  const [preview, setPreview] = useState(/** @type {Record<string, unknown> | null} */ (null));
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [metaRes, versionsRes] = await Promise.all([getCmMeta(), getCmVersions()]);
    if (metaRes?.success !== false) {
      setMeta(metaRes || {});
    }
    if (versionsRes?.success) {
      setVersions(Array.isArray(versionsRes.data) ? versionsRes.data : []);
    }
  }, [getCmMeta, getCmVersions]);

  useEffect(() => {
    void load();
  }, [load]);

  const publishEnabled = Boolean(meta?.publish_enabled);
  const publishMessage =
    (typeof meta?.publish_disabled_message === "string" && meta.publish_disabled_message) ||
    DEFAULT_PUBLISH_MESSAGE;

  const handleValidate = async () => {
    setBusy(true);
    try {
      const result = await validateCmDraft({});
      setValidation(result);
      if (result?.ok) toast.success("Validation passed");
      else toast.error(`${result?.error_count || 0} validation error(s)`);
    } finally {
      setBusy(false);
    }
  };

  const handlePreview = async () => {
    setBusy(true);
    try {
      const result = await buildCmPreviewPacket({ source: "draft" });
      if (!result?.success) {
        toast.error(result?.error || "Failed to build preview packet");
        return;
      }
      setPreview(result.data || null);
      toast.success("Preview packet ready (safe for Testing Lab)");
    } finally {
      setBusy(false);
    }
  };

  const handlePublishClick = async () => {
    if (!publishEnabled) {
      toast.error(publishMessage);
      return;
    }
    setBusy(true);
    try {
      const result = await publishCm();
      if (!result?.success) {
        toast.error(result?.error || result?.message || "Publish failed");
        return;
      }
      toast.success("Published");
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/content-managers"
          className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-800 mb-2"
        >
          <ArrowLeftIcon className="w-4 h-4" />
          AI Setup
        </Link>
        <h1 className="text-2xl font-bold text-slate-800">Preview / Validate / Publish</h1>
        <p className="text-slate-600 mt-1">
          Runtime mode: <span className="font-medium">{meta?.runtime_mode || "legacy"}</span>
        </p>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-2xl border border-slate-200 bg-white/90 p-5 space-y-4"
      >
        <div className="flex items-start gap-3">
          <LockClosedIcon className="w-6 h-6 text-slate-500 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-slate-800">
              {publishEnabled ? "Publish is enabled" : "Publish — unavailable"}
            </p>
            {!publishEnabled && <p className="text-sm text-slate-600 mt-1">{publishMessage}</p>}
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void handleValidate()}
            disabled={busy}
            className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
          >
            Validate all drafts
          </button>
          <button
            type="button"
            onClick={() => void handlePreview()}
            disabled={busy}
            className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
          >
            Build preview packet
          </button>
          <button
            type="button"
            onClick={() => void handlePublishClick()}
            disabled={!publishEnabled || busy}
            title={publishEnabled ? "Publish current drafts" : publishMessage}
            className={
              publishEnabled
                ? "rounded-xl bg-slate-800 text-white px-4 py-2.5 text-sm font-medium hover:bg-slate-700 disabled:opacity-60"
                : "rounded-xl border border-slate-200 bg-slate-100 px-4 py-2.5 text-sm font-medium text-slate-400 cursor-not-allowed"
            }
          >
            {publishEnabled ? "Publish" : "Publish — unavailable"}
          </button>
        </div>
      </motion.div>

      {validation && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-800">
            {validation.ok ? (
              <CheckCircleIcon className="w-5 h-5 text-emerald-600" />
            ) : (
              <ExclamationTriangleIcon className="w-5 h-5 text-rose-600" />
            )}
            Validation {validation.ok ? "passed" : "failed"}
          </div>
          {(validation.errors || []).map((err, idx) => (
            <p key={`e-${idx}`} className="text-sm text-rose-700">
              {String(err.message || err.code || "Error")}
            </p>
          ))}
          {(validation.warnings || []).map((warn, idx) => (
            <p key={`w-${idx}`} className="text-sm text-amber-700">
              {String(warn.message || warn.code || "Warning")}
            </p>
          ))}
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-800 mb-2">Versions</h2>
        {versions.length === 0 ? (
          <p className="text-sm text-slate-500">No published versions yet.</p>
        ) : (
          <ul className="space-y-1 text-sm text-slate-700">
            {versions.map((v) => (
              <li key={String(v.version_id)} className="font-mono">
                {String(v.version_id)}
              </li>
            ))}
          </ul>
        )}
      </div>

      {preview && (
        <div className="rounded-xl border border-slate-200 bg-slate-950 p-4 overflow-auto">
          <h2 className="text-sm font-semibold text-slate-100 mb-2">Preview packet</h2>
          <pre className="text-xs text-slate-200 whitespace-pre-wrap">
            {JSON.stringify(preview, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};

export default CmPublishPage;
