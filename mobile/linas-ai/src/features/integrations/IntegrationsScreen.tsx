import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, AppState, Linking, ScrollView, StyleSheet, Text } from 'react-native';
import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';
import { parseIntegrationsDeepLink } from '../../app/navigation';
import { tokenStore } from '../../auth/tokenStore';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, spacing } from '../../theme';
import { AuthGateModal } from '../auth/AuthGateModal';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import {
  IntegrationChannelCard,
  commentsBlocker,
  defaultToggles,
  type IntegrationRow,
} from './IntegrationChannelCard';
import { disconnectMetaBindings, startMetaOAuth } from './integrationsOAuth';
import {
  WhatsAppCloudCard,
  fetchWhatsAppCloudStatus,
  startWhatsAppCloudConnect,
  type WhatsAppCloudStatus,
} from './WhatsAppCloudCard';

type WaStatus = WhatsAppCloudStatus;

const TogglesSchema = z.object({
  dm: z.boolean(),
  comments: z.boolean(),
});

const CapabilityStateSchema = z
  .object({
    requested_enabled: z.boolean(),
    permission_present: z.boolean(),
    webhook_subscribed: z.boolean(),
    tenant_action_enabled: z.boolean().optional(),
    connection_healthy: z.boolean().optional(),
    live_verified: z.boolean(),
    effective_enabled: z.boolean(),
    missing_scopes: z.array(z.string()).optional(),
    blocker: z.string().nullable().optional(),
    blocker_code: z.string().nullable().optional(),
    blocker_message: z.string().nullable().optional(),
    status: z.string().optional(),
    last_checked_at: z.number().optional(),
  })
  .optional();

const RowSchema = z.object({
  platform: z.string(),
  label: z.string(),
  connected: z.boolean(),
  coming_soon: z.boolean().optional(),
  connectable: z.boolean().optional(),
  binding_ids: z.array(z.string()).optional(),
  toggles: TogglesSchema.optional(),
  comments_blocker: z.string().optional(),
  comments_state: CapabilityStateSchema,
  dm_state: CapabilityStateSchema,
  capabilities: z.record(z.string(), z.unknown()).optional(),
});

const ListSchema = z.object({
  success: z.literal(true),
  integrations: z.array(RowSchema),
});

const ToggleResponseSchema = z.object({
  success: z.literal(true),
  platform: z.string(),
  toggles: TogglesSchema,
  comments_state: CapabilityStateSchema,
  dm_state: CapabilityStateSchema,
});

type Row = z.infer<typeof RowSchema>;

type Props = {
  onRequestLogin?: () => void;
  onRequestRegister?: () => void;
};

const PLATFORM_LABEL: Record<string, StringKey> = {
  instagram: 'platformInstagram',
  facebook: 'platformFacebook',
  tiktok: 'platformTikTok',
  snapchat: 'platformSnapchat',
};

function isComingSoon(row: Row): boolean {
  if (row.coming_soon === true) return true;
  if (row.connectable === false) return true;
  return row.platform === 'tiktok' || row.platform === 'snapchat';
}

export function IntegrationsScreen({ onRequestLogin, onRequestRegister }: Props) {
  const { tr } = useI18n();
  const nav = useModuleNav();
  const [loading, setLoading] = useState(true);
  const [busyPlatform, setBusyPlatform] = useState<string | null>(null);
  const [busyToggle, setBusyToggle] = useState<{ platform: string; key: 'dm' | 'comments' } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [authGate, setAuthGate] = useState(false);
  const [waStatus, setWaStatus] = useState<WaStatus | null>(null);
  const [waBusy, setWaBusy] = useState(false);

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
      try {
        const wa = await fetchWhatsAppCloudStatus();
        setWaStatus(wa);
      } catch {
        setWaStatus(null);
      }
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
    }
  }, [tr]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (nav.activeArea === 'integrations') {
      void load();
    }
  }, [nav.areaFocusNonce, nav.activeArea, load]);

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
  }, [load, tr]);

  async function connectWhatsApp() {
    setWaBusy(true);
    setError(null);
    try {
      await startWhatsAppCloudConnect();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setAuthGate(true);
      else if (err instanceof ApiError && err.body && typeof err.body === 'object') {
        const body = err.body as { message?: unknown; error?: unknown };
        const msg = body.message;
        setError(typeof msg === 'string' && msg.trim() ? msg : tr('integrationsActionError'));
      } else setError(tr('integrationsActionError'));
    } finally {
      setWaBusy(false);
    }
  }

  async function setWhatsAppAi(connectionId: string, enabled: boolean) {
    setWaBusy(true);
    try {
      const path = enabled
        ? `/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/ai/enable`
        : `/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/ai/disable`;
      await apiFetch(path, { method: 'POST', schema: z.object({ success: z.literal(true) }) });
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setAuthGate(true);
      else setError(tr('integrationsActionError'));
    } finally {
      setWaBusy(false);
    }
  }

  async function manageMetaAccess(platform: 'instagram' | 'facebook') {
    setBusyPlatform(platform);
    setError(null);
    try {
      await startMetaOAuth(platform);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setAuthGate(true);
      else setError(tr('integrationsActionError'));
    } finally {
      setBusyPlatform(null);
    }
  }

  async function disconnectPlatform(row: Row) {
    const ids = row.binding_ids?.filter(Boolean) ?? [];
    if (ids.length === 0) {
      setError(tr('integrationsActionError'));
      return;
    }
    setBusyPlatform(row.platform);
    setError(null);
    try {
      await disconnectMetaBindings(ids);
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setAuthGate(true);
      else setError(tr('integrationsActionError'));
    } finally {
      setBusyPlatform(null);
    }
  }

  async function reconcileComments(row: Row) {
    const platform = row.platform === 'facebook' ? 'facebook' : 'instagram';
    setBusyPlatform(row.platform);
    setError(null);
    try {
      const res = await apiFetch(
        `/api/mobile/integrations/${encodeURIComponent(platform)}/reconcile-comments`,
        { method: 'POST', schema: ToggleResponseSchema },
      );
      setRows((curr) =>
        curr.map((r) =>
          r.platform === row.platform
            ? {
                ...r,
                toggles: res.toggles,
                comments_state: res.comments_state ?? r.comments_state,
                dm_state: res.dm_state ?? r.dm_state,
                comments_blocker:
                  res.comments_state?.blocker_code ?? res.comments_state?.blocker ?? undefined,
              }
            : r,
        ),
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setAuthGate(true);
      else if (err instanceof ApiError && err.body && typeof err.body === 'object') {
        const body = err.body as { message?: unknown; reauthorize_required?: unknown };
        const msg = body.message;
        setError(typeof msg === 'string' && msg.trim() ? msg : tr('integrationsActionError'));
        if (body.reauthorize_required === true) await manageMetaAccess(platform);
      } else setError(tr('integrationsActionError'));
    } finally {
      setBusyPlatform(null);
    }
  }

  async function setToggle(row: Row, key: 'dm' | 'comments', value: boolean) {
    const previous = defaultToggles(row as IntegrationRow);
    const platform = row.platform === 'facebook' ? 'facebook' : 'instagram';

    if (key === 'comments' && value === true) {
      const blocker = commentsBlocker(row as IntegrationRow);
      if (blocker === 'missing_comment_permissions' || blocker === 'reauthorization_required') {
        const missing = row.comments_state?.missing_scopes?.filter(Boolean) ?? [];
        setError(
          missing.length
            ? `${tr('commentsBlockerMissingPermissions')} Missing: ${missing.join(', ')}.`
            : tr('commentsBlockerMissingPermissions'),
        );
        await manageMetaAccess(platform);
        return;
      }
      if (blocker === 'meta_approval_required') {
        setError(tr('commentsBlockerMetaApproval'));
        return;
      }
      if (blocker === 'missing_comment_webhook') {
        await reconcileComments(row);
        return;
      }
      if (blocker === 'connect_channel_first') {
        setError(tr('commentsBlockerConnectFirst'));
        await manageMetaAccess(platform);
        return;
      }
    }

    setBusyToggle({ platform: row.platform, key });
    setError(null);
    setRows((curr) =>
      curr.map((r) =>
        r.platform === row.platform
          ? { ...r, toggles: { ...defaultToggles(r as IntegrationRow), [key]: value } }
          : r,
      ),
    );
    try {
      const res = await apiFetch(`/api/mobile/integrations/${encodeURIComponent(row.platform)}/toggles`, {
        method: 'PATCH',
        body: JSON.stringify({ [key]: value }),
        schema: ToggleResponseSchema,
      });
      setRows((curr) =>
        curr.map((r) =>
          r.platform === row.platform
            ? {
                ...r,
                toggles: res.toggles,
                comments_state: res.comments_state ?? r.comments_state,
                dm_state: res.dm_state ?? r.dm_state,
                comments_blocker:
                  res.comments_state?.blocker_code ?? res.comments_state?.blocker ?? undefined,
              }
            : r,
        ),
      );
    } catch (err) {
      setRows((curr) =>
        curr.map((r) => (r.platform === row.platform ? { ...r, toggles: previous } : r)),
      );
      if (err instanceof ApiError && err.status === 401) setAuthGate(true);
      else if (err instanceof ApiError && err.body && typeof err.body === 'object') {
        const body = err.body as {
          message?: unknown;
          error?: unknown;
          reauthorize_required?: unknown;
        };
        const msg = body.message;
        const code = typeof body.error === 'string' ? body.error : '';
        setError(typeof msg === 'string' && msg.trim() ? msg : tr('integrationsToggleError'));
        if (body.reauthorize_required === true || code === 'COMMENT_SCOPES_MISSING') {
          await manageMetaAccess(platform);
        }
      } else setError(tr('integrationsToggleError'));
    } finally {
      setBusyToggle(null);
    }
  }

  function platformTitle(row: Row): string {
    const key = PLATFORM_LABEL[row.platform];
    return key ? tr(key) : row.label;
  }

  return (
    <ScreenChrome title={tr('integrations')} subtitle={tr('integrationsSub')}>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {notice ? <Text style={styles.notice}>{notice}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <PrimaryButton
        label={tr('refreshConnectionStatus')}
        onPress={() => void load()}
        loading={loading}
        variant="ghost"
      />
      <Text style={{ color: colors.textMuted, fontSize: 12, marginBottom: spacing.md }}>
        {tr('refreshConnectionStatusHint')}
      </Text>
      <ScrollView contentContainerStyle={styles.list}>
        <WhatsAppCloudCard
          status={waStatus}
          loading={loading}
          busy={waBusy}
          onRefresh={() => void load()}
          onConnect={() => void connectWhatsApp()}
          onEnableAi={(id) => void setWhatsAppAi(id, true)}
          onDisableAi={(id) => void setWhatsAppAi(id, false)}
        />
        {rows
          .filter((row) => row.platform === 'instagram' || row.platform === 'facebook')
          .map((row) => (
            <IntegrationChannelCard
              key={row.platform}
              row={row as IntegrationRow}
              title={platformTitle(row)}
              soon={isComingSoon(row)}
              busy={busyPlatform === row.platform}
              busyToggleKey={busyToggle?.platform === row.platform ? busyToggle.key : null}
              actionsDisabled={busyPlatform !== null || busyToggle !== null}
              tr={tr}
              onToggle={(key, value) => void setToggle(row, key, value)}
              onManageMetaAccess={() =>
                void manageMetaAccess(row.platform === 'facebook' ? 'facebook' : 'instagram')
              }
              onReconcileComments={() => void reconcileComments(row)}
              onConnect={() =>
                void manageMetaAccess(row.platform === 'facebook' ? 'facebook' : 'instagram')
              }
              onDisconnect={() => void disconnectPlatform(row)}
            />
          ))}
      </ScrollView>

      <AuthGateModal
        visible={authGate}
        onClose={() => {
          setAuthGate(false);
          nav.goChat();
        }}
        onLogin={() => {
          setAuthGate(false);
          onRequestLogin?.();
        }}
        onRegister={() => {
          setAuthGate(false);
          onRequestRegister?.();
        }}
      />
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 40, gap: spacing.md },
  notice: { color: colors.accent, marginBottom: spacing.md, fontFamily: fonts.body },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
