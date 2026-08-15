import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { AppState, Linking } from 'react-native';

import { ApiError, apiFetch } from '../../api/client';
import { parseIntegrationsDeepLink } from '../../app/navigation';
import { tokenStore } from '../../auth/tokenStore';
import type { StringKey } from '../../i18n/locales/en';
import { ListSchema, type IntegrationListRow } from './integrationsSchemas';

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
  const skipNextAreaFocusLoad = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const access = await tokenStore.getAccessToken();
      if (!access) {
        setAuthGate(true);
        setRows([]);
        setError(null);
        return;
      }
      const data = await apiFetch('/api/mobile/integrations', { schema: ListSchema });
      setRows(data.integrations);
      await refreshWhatsApp();
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setAuthGate(true);
        setError(null);
      } else {
        setError(tr('integrationsLoadError'));
      }
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
      if (parsed.waConnection === 'success' || parsed.metaConnection === 'success') {
        setNotice(parsed.waConnection === 'success' ? tr('waOAuthSuccess') : tr('metaOAuthSuccess'));
        setError(null);
      } else if (parsed.waConnection === 'cancelled' || parsed.metaConnection === 'cancelled') {
        setNotice(null);
        setError(parsed.waConnection === 'cancelled' ? tr('waOAuthCancelled') : tr('metaOAuthCancelled'));
      } else if (parsed.waConnection === 'failed' || parsed.metaConnection === 'failed') {
        setNotice(null);
        setError(parsed.waConnection === 'failed' ? tr('waOAuthFailed') : tr('metaOAuthFailed'));
      }
      void load();
    };
    void Linking.getInitialURL().then(applyMetaResult);
    const sub = Linking.addEventListener('url', (event) => applyMetaResult(event.url));
    return () => sub.remove();
  }, [load, tr, setError]);

  return { loading, hasLoadedOnce, notice, setNotice, rows, setRows, load };
}
