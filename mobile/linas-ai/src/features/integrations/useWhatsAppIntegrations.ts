import { useCallback, useState } from 'react';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import {
  fetchWhatsAppCloudStatus,
  startWhatsAppCloudConnect,
  WhatsAppConnectError,
  type WhatsAppCloudStatus,
} from './WhatsAppCloudCard';
import { setWhatsAppAiEnabled } from './whatsappCloudApi';

type Opts = {
  onAuthGate: () => void;
  onError: (message: string | null) => void;
};

/** WhatsApp Cloud status + connect/AI actions for Integrations. */
export function useWhatsAppIntegrations({ onAuthGate, onError }: Opts) {
  const { tr } = useI18n();
  const [waStatus, setWaStatus] = useState<WhatsAppCloudStatus | null>(null);
  const [waBusy, setWaBusy] = useState(false);

  const refreshWhatsApp = useCallback(async () => {
    try {
      const wa = await fetchWhatsAppCloudStatus();
      setWaStatus(wa);
    } catch {
      setWaStatus(null);
    }
  }, []);

  async function connectWhatsApp() {
    if (waBusy) return;
    if (waStatus?.flags?.embedded_signup_config_configured === false) {
      onError(tr('waConnectConfigMissing'));
      return;
    }
    setWaBusy(true);
    onError(null);
    try {
      await startWhatsAppCloudConnect();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onAuthGate();
      else if (err instanceof WhatsAppConnectError) {
        if (err.code === 'cancelled') onError(tr('waOAuthCancelled'));
        else if (err.code === 'connect_in_progress') onError(tr('waConnectInProgress'));
        else if (err.code === 'invalid_authorization_url') onError(tr('waConnectConfigMissing'));
        else if (err.code === 'failed') onError(tr('waOAuthFailed'));
        else onError(tr('waConnectBrowserUnavailable'));
      } else if (err instanceof ApiError && err.body && typeof err.body === 'object') {
        const body = err.body as { message?: unknown; error?: unknown };
        const msg = body.message;
        if (typeof msg === 'string' && msg.trim()) onError(msg);
        else if (body.error === 'WHATSAPP_PILOT_REQUIRED') onError(tr('waStateAwaitingMetaApproval'));
        else onError(tr('integrationsActionError'));
      } else onError(tr('integrationsActionError'));
    } finally {
      setWaBusy(false);
    }
  }

  async function setWhatsAppAi(connectionId: string, enabled: boolean, after?: () => Promise<void>) {
    if (waBusy) return;
    setWaBusy(true);
    try {
      await setWhatsAppAiEnabled(connectionId, enabled);
      await after?.();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onAuthGate();
      else onError(tr('integrationsActionError'));
    } finally {
      setWaBusy(false);
    }
  }

  return {
    waStatus,
    waBusy,
    setWaBusy,
    setWaStatus,
    refreshWhatsApp,
    connectWhatsApp,
    setWhatsAppAi,
  };
}
