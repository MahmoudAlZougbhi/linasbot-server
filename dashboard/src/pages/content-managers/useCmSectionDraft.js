import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { useApi } from "../../hooks/useApi";
import { asRecord } from "./cmDraftHelpers";

/**
 * Shared draft load/save/validate for a CM section.
 * @param {string} section
 */
export function useCmSectionDraft(section) {
  const { getCmDraft, putCmDraft, validateCmDraft, getCmMeta } = useApi();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [etag, setEtag] = useState(/** @type {string | null} */ (null));
  const [payload, setPayload] = useState(/** @type {Record<string, unknown>} */ ({}));
  const [meta, setMeta] = useState(/** @type {Record<string, unknown> | null} */ (null));
  const [conflict, setConflict] = useState(/** @type {string | null} */ (null));
  const [validation, setValidation] = useState(
    /** @type {{ ok?: boolean; errors?: Array<Record<string, unknown>>; warnings?: Array<Record<string, unknown>> } | null} */ (
      null
    )
  );
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setConflict(null);
    try {
      const [draftRes, metaRes] = await Promise.all([getCmDraft(section), getCmMeta()]);
      setMeta(metaRes && typeof metaRes === "object" ? /** @type {Record<string, unknown>} */ (metaRes) : null);
      if (!draftRes?.success || !draftRes.data) {
        toast.error(draftRes?.error || `Failed to load ${section}`);
        return;
      }
      const envelope = /** @type {Record<string, unknown>} */ (draftRes.data);
      const raw = envelope.payload ?? envelope.data ?? {};
      setPayload(asRecord(raw));
      setEtag(
        typeof draftRes.etag === "string"
          ? draftRes.etag
          : typeof envelope.etag === "string"
            ? envelope.etag
            : null
      );
      setDirty(false);
    } finally {
      setLoading(false);
    }
  }, [getCmDraft, getCmMeta, section]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onBeforeUnload = (/** @type {BeforeUnloadEvent} */ event) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  /**
   * @param {Record<string, unknown>} next
   */
  const updatePayload = (next) => {
    setPayload(next);
    setDirty(true);
  };

  /**
   * @param {Record<string, unknown>} [override]
   */
  const save = async (override) => {
    const body = override || payload;
    if (!etag) {
      toast.error("Missing ETag — reload before saving");
      return false;
    }
    setSaving(true);
    setConflict(null);
    try {
      const res = await putCmDraft(section, body, etag);
      if (res?.conflict) {
        setConflict(res.error || "Someone else saved this section. Reload and retry.");
        toast.error("Stale version — reload required");
        return false;
      }
      if (!res?.success) {
        toast.error(res?.error || "Save failed");
        return false;
      }
      toast.success("Draft saved");
      if (typeof res.etag === "string") setEtag(res.etag);
      if (res.data) {
        const envelope = /** @type {Record<string, unknown>} */ (res.data);
        setPayload(asRecord(envelope.payload ?? envelope.data ?? body));
      } else {
        setPayload(body);
      }
      setDirty(false);
      return true;
    } finally {
      setSaving(false);
    }
  };

  const validate = async () => {
    setValidating(true);
    try {
      const res = await validateCmDraft();
      setValidation(res || null);
      if (res?.ok) toast.success("Validation passed");
      else toast.error(`Validation found ${res?.error_count ?? "some"} issue(s)`);
      return res;
    } finally {
      setValidating(false);
    }
  };

  return {
    loading,
    saving,
    validating,
    etag,
    payload,
    setPayload: updatePayload,
    meta,
    conflict,
    validation,
    dirty,
    load,
    save,
    validate,
  };
}
