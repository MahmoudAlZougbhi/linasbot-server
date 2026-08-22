import { useCallback } from 'react';

import { ApiError } from '../../api/client';
import type { StringKey } from '../../i18n/locales/en';
import { MetaOAuthConnectError, startMetaOAuth } from './integrationsOAuth';
import {
  metaOAuthFailureMessage,
  metaOAuthFailureReasonFromApiBody,
} from '../../app/integrationsDeepLink';
import { shouldApplyMetaSessionFeedback } from './integrationsFeedback';
import type { IntegrationsLoadResult } from './useIntegrationsLoad';
import type { IntegrationListRow } from './integrationsSchemas';

type Args = {
  tr: (key: StringKey) => string;
  load: () => Promise<IntegrationsLoadResult>;
  setBusyPlatform: (platform: string | null) => void;
  setError: (message: string | null) => void;
  setNotice: (message: string | null) => void;
  setAuthGate: (open: boolean) => void;
  metaResultSequence: { current: number };
};

export function useMetaPlatformConnect({
  tr,
  load,
  setBusyPlatform,
  setError,
  setNotice,
  setAuthGate,
  metaResultSequence,
}: Args) {
  const connectPlatform = useCallback(
    async (platform: 'instagram' | 'facebook') => {
      const deepLinkSequenceAtStart = metaResultSequence.current;
      setBusyPlatform(platform);
      setError(null);
      setNotice(null);
      try {
        const session = await startMetaOAuth(platform);
        let loaded = await load();
        if (!loaded.ok) return;
        let row = findRow(loaded.rows, platform);
        if (!row?.connected) {
          await new Promise((resolve) => setTimeout(resolve, 600));
          loaded = await load();
          if (!loaded.ok) return;
          row = findRow(loaded.rows, platform);
        }
        if (row?.connected) {
          setNotice(tr('metaOAuthSuccess'));
          setError(null);
          return;
        }
        if (
          !shouldApplyMetaSessionFeedback(
            deepLinkSequenceAtStart,
            metaResultSequence.current,
          )
        ) {
          return;
        }
        if (session.outcome === 'cancelled') setError(tr('metaOAuthCancelled'));
        else if (session.outcome === 'failed') {
          setError(metaOAuthFailureMessage(tr, session.reason, platform));
        } else setError(tr('metaOAuthIncomplete'));
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) setAuthGate(true);
        else if (err instanceof MetaOAuthConnectError) {
          setError(tr('integrationsActionError'));
        } else if (err instanceof ApiError) {
          const reason = metaOAuthFailureReasonFromApiBody(err.body);
          setError(
            reason
              ? metaOAuthFailureMessage(tr, reason, platform)
              : tr('integrationsActionError'),
          );
        } else setError(tr('integrationsActionError'));
      } finally {
        setBusyPlatform(null);
      }
    },
    [load, metaResultSequence, setAuthGate, setBusyPlatform, setError, setNotice, tr],
  );

  return { connectPlatform };
}

function findRow(rows: IntegrationListRow[], platform: string) {
  return rows.find((item) => item.platform === platform);
}
