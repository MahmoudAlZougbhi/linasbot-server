import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { useApi } from "../../hooks/useApi";
import { findCmSectionBySlug } from "./cmSections";

const CmSectionPage = () => {
  const { sectionSlug = "" } = useParams();
  const card = findCmSectionBySlug(sectionSlug);
  const {
    getCmDraft,
    putCmDraft,
    validateCmDraft,
    getCmMeta,
  } = useApi();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [etag, setEtag] = useState(/** @type {string | null} */ (null));
  const [notes, setNotes] = useState("");
  const [dataJson, setDataJson] = useState("{}");
  const [conflict, setConflict] = useState(/** @type {{ message: string; currentEtag?: string } | null} */ (null));
  const [validation, setValidation] = useState(
    /** @type {{ ok?: boolean; errors?: Array<Record<string, unknown>>; warnings?: Array<Record<string, unknown>> } | null} */ (
      null
    )
  );
  const [publishMessage, setPublishMessage] = useState(
    "Publishing is not enabled yet. This phase saves drafts only."
  );

  const loadDraft = useCallback(async () => {
    if (!card?.section) return;
    setLoading(true);
    setConflict(null);
    try {
      const [draftRes, metaRes] = await Promise.all([
        getCmDraft(card.section),
        getCmMeta(),
      ]);
      if (metaRes?.publish_disabled_message) {
        setPublishMessage(String(metaRes.publish_disabled_message));
      }
      if (!draftRes?.success || !draftRes.data) {
        toast.error(draftRes?.error || "Failed to load draft");
        return;
      }
      /** @type {Record<string, unknown>} */
      const envelope = draftRes.data;
      const rawPayload = envelope.payload ?? envelope.data;
      const payload =
        rawPayload && typeof rawPayload === "object" && !Array.isArray(rawPayload)
          ? /** @type {Record<string, unknown>} */ (rawPayload)
          : {};
      setEtag(
        typeof draftRes.etag === "string"
          ? draftRes.etag
          : typeof envelope.etag === "string"
            ? envelope.etag
            : null
      );
      setNotes(typeof payload.notes === "string" ? payload.notes : "");
      setDataJson(JSON.stringify(payload, null, 2));
    } finally {
      setLoading(false);
    }
  }, [card?.section, getCmDraft, getCmMeta]);

  useEffect(() => {
    void loadDraft();
  }, [loadDraft]);

  if (!card) {
    return <Navigate to="/content-managers" replace />;
  }
  if (card.section === null) {
    return <Navigate to="/content-managers/publish" replace />;
  }

  /** @returns {Record<string, unknown> | null} */
  const parseData = () => {
    try {
      const parsed = JSON.parse(dataJson);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        toast.error("Draft data must be a JSON object");
        return null;
      }
      return { ...parsed, notes };
    } catch {
      toast.error("Draft JSON is invalid");
      return null;
    }
  };

  const handleSave = async () => {
    const data = parseData();
    if (!data || !card.section) return;
    if (!etag) {
      toast.error("Missing ETag — reload the draft before saving");
      return;
    }
    setSaving(true);
    setConflict(null);
    try {
      const result = await putCmDraft(card.section, { payload: data }, etag);
      if (result?.conflict) {
        setConflict({
          message: result.message || "Draft conflict — reload and try again.",
          currentEtag: result.current_etag,
        });
        toast.error("Save conflict: draft was changed elsewhere");
        return;
      }
      if (!result?.success) {
        toast.error(result?.error || "Failed to save draft");
        return;
      }
      const envelope = result.data || {};
      setEtag(
        typeof result.etag === "string"
          ? result.etag
          : typeof envelope.etag === "string"
            ? envelope.etag
            : etag
      );
      toast.success("Draft saved");
    } finally {
      setSaving(false);
    }
  };

  const handleValidate = async () => {
    const data = parseData();
    if (!data || !card.section) return;
    setValidating(true);
    try {
      const result = await validateCmDraft({ section: card.section, payload: data });
      if (!result?.success && result?.error) {
        toast.error(result.error);
        return;
      }
      setValidation(result);
      if (result?.ok) {
        toast.success("Validation passed");
      } else {
        toast.error(`${result?.error_count || 0} validation error(s)`);
      }
    } finally {
      setValidating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Link
            to="/content-managers"
            className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-800 mb-2"
          >
            <ArrowLeftIcon className="w-4 h-4" />
            Content Managers
          </Link>
          <h1 className="text-2xl font-bold text-slate-800">{card.name}</h1>
          <p className="text-slate-600 mt-1">{card.description}</p>
        </div>
        <div className="text-xs text-slate-500 font-mono bg-slate-100 rounded-lg px-3 py-2">
          ETag: {etag || "—"}
        </div>
      </div>

      {conflict && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 flex gap-3">
          <ExclamationTriangleIcon className="w-6 h-6 text-amber-600 shrink-0" />
          <div className="space-y-2">
            <p className="font-medium text-amber-900">Draft conflict</p>
            <p className="text-sm text-amber-800">{conflict.message}</p>
            {conflict.currentEtag && (
              <p className="text-xs font-mono text-amber-700">Current ETag: {conflict.currentEtag}</p>
            )}
            <button
              type="button"
              onClick={() => void loadDraft()}
              className="text-sm font-medium text-amber-900 underline"
            >
              Reload latest draft
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-slate-600 text-sm py-12 text-center">Loading draft…</div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">Author notes</span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-300"
              placeholder="One natural language. Notes never override structured fields."
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700">Section data (JSON)</span>
            <textarea
              value={dataJson}
              onChange={(e) => setDataJson(e.target.value)}
              rows={16}
              spellCheck={false}
              className="w-full rounded-xl border border-slate-200 bg-slate-950 text-slate-100 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
          </label>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={saving}
              className="rounded-xl bg-slate-800 text-white px-4 py-2.5 text-sm font-medium hover:bg-slate-700 disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save Draft"}
            </button>
            <button
              type="button"
              onClick={() => void handleValidate()}
              disabled={validating}
              className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
            >
              {validating ? "Validating…" : "Validate"}
            </button>
            <button
              type="button"
              disabled
              title={publishMessage}
              className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-2.5 text-sm font-medium text-slate-400 cursor-not-allowed"
            >
              Publish — unavailable
            </button>
          </div>

          <p className="text-sm text-slate-500 max-w-2xl">{publishMessage}</p>

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
        </motion.div>
      )}
    </div>
  );
};

export default CmSectionPage;
