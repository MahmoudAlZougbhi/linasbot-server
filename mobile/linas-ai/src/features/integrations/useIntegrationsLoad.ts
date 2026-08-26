import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { AppState, Linking } from 'react-native';

import { ApiError, apiFetch } from '../../api/client';
import { parseIntegrationsDeepLink, metaOAuthFailureMessage } from '../../app/navigation';
import { tokenStore } from '../../auth/tokenStore';
import type { StringKey } from '../../i18n/locales/en';
import {
  errorAfterIntegrationLoadFailure,
  errorAfterIntegrationLoadSuccess,
} from './integrationsFeedback';
import { ListSchema, type IntegrationListRow } from './integrationsSchemas';
import { hasWebChatCardSnapshot, prefetchWebChatCardSnapshot } from './webChatCardLoader';

export type IntegrationsLoadResult = { ok: boolean; rows: IntegrationListRow[] };

type Args = {
  tr: (key: StringKey) => string;
  refreshWhatsApp: () => Promise<void>;
  activeArea: string | null;
  areaFocusNonce: number;
  setError: Dispatch<SetStateAction<string | null>>;
  setAuthGate: Dispatch<SetStateAction<boolean>>;
};

export function useIntegrationsLoad({
  tr,
  refreshWhatsApp,
  activeArea,
  areaFocusNonce,
  setError,
  setAuthGate,
}: Args) {
  const [loading, setLoading] = useState(false);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [rows, setRows] = useState<IntegrationListRow[]>([]);
  const [webChatReady, setWebChatReady] = useState(hasWebChatCardSnapshot);
  const skipNextAreaFocusLoad = useRef(false);
  const metaResultSequence = useRef(0);

  const load = useCallback(async (): Promise<IntegrationsLoadResult> => {
    setLoading(true);
    try {
      const access = await tokenStore.getAccessToken();
      if (!access) {
        setAuthGate(true);
        setRows([]);
        setWebChatReady(true);
        setError((current) =>
          errorAfterIntegrationLoadSuccess(current, tr('integrationsLoadError')),
        );
        return { ok: false, rows: [] };
      }
      const data = await apiFetch('/api/mobile/integrations', { schema: ListSchema });
      setRows(data.integrations);
      // List succeeded — never keep a stale "could not load" while channels render.
      setError((current) =>
        errorAfterIntegrationLoadSuccess(current, tr('integrationsLoadError')),
      );
      // WhatsApp / Website chat are separate cards; their failures must not fail the list.
      await Promise.all([refreshWhatsApp(), prefetchWebChatCardSnapshot()]);
      setWebChatReady(true);
      return { ok: true, rows: data.integrations };
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setAuthGate(true);
        setError((current) =>
          errorAfterIntegrationLoadSuccess(current, tr('integrationsLoadError')),
        );
      } else {
        setError((current) =>
          errorAfterIntegrationLoadFailure(current, tr('integrationsLoadError')),
        );
      }
      setWebChatReady(true);
      return { ok: false, rows: [] };
    } finally {
      setLoading(false);
      setHasLoadedOnce(true);
    }
  }, [tr, refreshWhatsApp, setAuthGate, setError]);

  useEffect(() => {
    skipNextAreaFocusLoad.current = true;
    void load();
  }, [load]);

  useEffect(() => {
    if (activeArea !== 'integrations') return;
    if (skipNextAreaFocusLoad.current) {
      skipNextAreaFocusLoad.current = false;
      return;
    }
    void load();
  }, [areaFocusNonce, activeArea, load]);

  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') void load();
    });
    return () => sub.remove();
  }, [load]);

  useEffect(() => {
    const applyMetaResult = (url: string | null) => {
      const parsed = parseIntegrationsDeepLink(url);
      if (!parsed) return;
      if (parsed.metaConnection !== null) metaResultSequence.current += 1;
      if (parsed.waConnection === 'success' || parsed.metaConnection === 'success') {
        setNotice(parsed.waConnection === 'success' ? tr('waOAuthSuccess') : tr('metaOAuthSuccess'));
        setError(null);
      } else if (parsed.waConnection === 'cancelled' || parsed.metaConnection === 'cancelled') {
        setNotice(null);
        setError(parsed.waConnection === 'cancelled' ? tr('waOAuthCancelled') : tr('metaOAuthCancelled'));
      } else if (parsed.waConnection === 'failed' || parsed.metaConnection === 'failed') {
        setNotice(null);
        if (parsed.waConnection === 'failed') {
          if (parsed.waError === 'coexistence_flow_required') setError(tr('waWrongFlow'));
          else if (parsed.waError === 'meta_advanced_access_required') setError(tr('waAdvancedAccess'));
          else if (parsed.waError === 'session_timeout' || parsed.waError === 'embedded_signup_timeout') {
            setError(tr('waSessionTimeout'));
          } else setError(tr('waOAuthFailed'));
        } else setError(metaOAuthFailureMessage(tr, parsed.metaReason, parsed.metaChannel));
      }
      void load();
    };
    void Linking.getInitialURL().then(applyMetaResult);
    const sub = Linking.addEventListener('url', (event) => applyMetaResult(event.url));
    return () => sub.remove();
  }, [load, tr, setError]);

  return {
    loading,
    hasLoadedOnce,
    webChatReady,
    notice,
    setNotice,
    rows,
    setRows,
    load,
    metaResultSequence,
  };
}
