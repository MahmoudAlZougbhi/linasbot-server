import { useCallback, useState } from 'react';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import {
  fetchWhatsAppCloudStatus,
  startWhatsAppCloudConnect,
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
    setWaBusy(true);
    onError(null);
    try {
      await startWhatsAppCloudConnect();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onAuthGate();
      else if (err instanceof ApiError && err.body && typeof err.body === 'object') {
        const body = err.body as { message?: unknown };
        const msg = body.message;
        onError(typeof msg === 'string' && msg.trim() ? msg : tr('integrationsActionError'));
      } else onError(tr('integrationsActionError'));
    } finally {
      setWaBusy(false);
    }
  }

  async function setWhatsAppAi(connectionId: string, enabled: boolean, after?: () => Promise<void>) {
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
