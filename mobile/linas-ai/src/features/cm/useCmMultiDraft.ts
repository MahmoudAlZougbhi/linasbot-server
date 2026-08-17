import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '../../api/client';
import {
  applyProposedItem,
  mergeProposalPatch,
  type CmProposalReview,
} from './cmProposalReview';
import { getCmDraft, putCmDraft } from './cmApi';
import { sanitizeCmSectionPayload } from './stripProvenanceHeaders';

type SectionDraft = {
  payload: Record<string, unknown>;
  etag: string | null;
  dirty: boolean;
};

/** Load/save multiple CM draft sections as one composite editor (e.g. AI Basics + Style). */
export function useCmMultiDraft(
  sections: readonly string[],
  proposalReview?: CmProposalReview | null,
) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, SectionDraft>>({});
  const [proposalActive, setProposalActive] = useState(false);
  const sectionKey = sections.join(',');

  const load = useCallback(async () => {
    const names = sectionKey.split(',').filter(Boolean);
    setLoading(true);
    setError(null);
    setConflict(null);
    try {
      const loaded = await Promise.all(names.map((section) => getCmDraft(section)));
      const next: Record<string, SectionDraft> = {};
      let overlay = false;
      names.forEach((section, idx) => {
        const draft = loaded[idx];
        let payload = sanitizeCmSectionPayload(section, draft.payload);
        if (proposalReview && proposalReview.section === section) {
          if (proposalReview.proposedItem) {
            const idKey = section === 'faq' ? 'qa_group_id' : 'id';
            payload = applyProposedItem(draft.payload, proposalReview.proposedItem, idKey);
            overlay = true;
          } else if (proposalReview.patch && Object.keys(proposalReview.patch).length) {
            payload = mergeProposalPatch(draft.payload, proposalReview.patch);
            overlay = true;
          }
        }
        next[section] = { payload, etag: draft.etag, dirty: overlay };
      });
      setDrafts(next);
      setProposalActive(overlay);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.status === 401
            ? 'Sign in required to edit AI Setup.'
            : err.status === 403
              ? 'Your account needs contentManagers permission.'
              : err.message
          : 'Could not load draft.';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [proposalReview, sectionKey]);

  useEffect(() => {
    void load();
  }, [load]);

  const setPayload = useCallback((section: string, next: Record<string, unknown>) => {
    setDrafts((prev) => {
      const cur = prev[section];
      if (!cur) return prev;
      return { ...prev, [section]: { ...cur, payload: next, dirty: true } };
    });
    setProposalActive(false);
  }, []);

  const dirty = Object.values(drafts).some((d) => d.dirty);
  const canSave = sections.every((s) => drafts[s]?.etag);

  const save = useCallback(async () => {
    if (!canSave) {
      setError('Missing ETag — reload before saving.');
      return false;
    }
    setSaving(true);
    setError(null);
    setConflict(null);
    try {
      const updated: Record<string, SectionDraft> = { ...drafts };
      for (const section of sections) {
        const cur = drafts[section];
        if (!cur?.etag) continue;
        const draft = await putCmDraft(section, cur.payload, cur.etag);
        updated[section] = {
          payload: sanitizeCmSectionPayload(section, draft.payload),
          etag: draft.etag,
          dirty: false,
        };
      }
      setDrafts(updated);
      setProposalActive(false);
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setConflict('Someone else saved this section. Reload and retry.');
        return false;
      }
      setError(err instanceof Error ? err.message : 'Save failed.');
      return false;
    } finally {
      setSaving(false);
    }
  }, [canSave, drafts, sections]);

  return {
    loading,
    saving,
    error,
    conflict,
    drafts,
    dirty,
    canSave,
    proposalActive,
    setPayload,
    load,
    save,
  };
}
