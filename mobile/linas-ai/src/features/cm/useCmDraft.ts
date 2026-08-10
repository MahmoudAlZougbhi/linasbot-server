import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '../../api/client';
import {
  applyProposedItem,
  mergeProposalPatch,
  type CmProposalReview,
} from './cmProposalReview';
import { getCmDraft, putCmDraft } from './cmApi';

export function useCmDraft(section: string, proposalReview?: CmProposalReview | null) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [etag, setEtag] = useState<string | null>(null);
  const [payload, setPayloadState] = useState<Record<string, unknown>>({});
  const [dirty, setDirty] = useState(false);
  const [proposalActive, setProposalActive] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setConflict(null);
    try {
      const draft = await getCmDraft(section);
      let next = draft.payload;
      let overlay = false;
      if (proposalReview && proposalReview.section === section) {
        if (proposalReview.proposedItem) {
          const idKey = section === 'faq' ? 'qa_group_id' : 'id';
          next = applyProposedItem(draft.payload, proposalReview.proposedItem, idKey);
          overlay = true;
        } else if (proposalReview.patch && Object.keys(proposalReview.patch).length) {
          next = mergeProposalPatch(draft.payload, proposalReview.patch);
          overlay = true;
        }
      }
      setPayloadState(next);
      setEtag(draft.etag);
      setDirty(overlay);
      setProposalActive(overlay);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.status === 401
            ? 'Sign in required to edit Content Management.'
            : err.status === 403
              ? 'Your account needs contentManagers permission.'
              : err.message
          : 'Could not load draft.';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [proposalReview, section]);

  useEffect(() => {
    void load();
  }, [load]);

  const setPayload = useCallback((next: Record<string, unknown>) => {
    setPayloadState(next);
    setDirty(true);
    setProposalActive(false);
  }, []);

  const patchPayload = useCallback((patch: Record<string, unknown>) => {
    setPayloadState((prev) => {
      setDirty(true);
      setProposalActive(false);
      return { ...prev, ...patch };
    });
  }, []);

  const save = useCallback(async () => {
    if (!etag) {
      setError('Missing ETag — reload before saving.');
      return false;
    }
    setSaving(true);
    setError(null);
    setConflict(null);
    try {
      const draft = await putCmDraft(section, payload, etag);
      setPayloadState(draft.payload);
      setEtag(draft.etag);
      setDirty(false);
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
  }, [etag, payload, section]);

  return {
    loading,
    saving,
    error,
    conflict,
    etag,
    payload,
    dirty,
    proposalActive,
    setPayload,
    patchPayload,
    load,
    save,
  };
}
