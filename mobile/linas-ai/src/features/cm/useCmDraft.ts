import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '../../api/client';
import { getCmDraft, putCmDraft } from './cmApi';

export function useCmDraft(section: string) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [etag, setEtag] = useState<string | null>(null);
  const [payload, setPayloadState] = useState<Record<string, unknown>>({});
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setConflict(null);
    try {
      const draft = await getCmDraft(section);
      setPayloadState(draft.payload);
      setEtag(draft.etag);
      setDirty(false);
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
  }, [section]);

  useEffect(() => {
    void load();
  }, [load]);

  const setPayload = useCallback((next: Record<string, unknown>) => {
    setPayloadState(next);
    setDirty(true);
  }, []);

  const patchPayload = useCallback((patch: Record<string, unknown>) => {
    setPayloadState((prev) => {
      setDirty(true);
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
    setPayload,
    patchPayload,
    load,
    save,
  };
}
