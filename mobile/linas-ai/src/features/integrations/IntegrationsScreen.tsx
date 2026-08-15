import { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text } from 'react-native';

import { ApiError, apiFetch } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, spacing } from '../../theme';
import { AuthGateModal } from '../auth/AuthGateModal';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import {
  IntegrationAccountSheet,
  type IntegrationSheetTarget,
} from './IntegrationAccountSheet';
import {
  IntegrationChannelCard,
  channelSubtitle,
  commentsBlocker,
  defaultToggles,
  type IntegrationRow,
} from './IntegrationChannelCard';
import { IntegrationRefreshButton } from './IntegrationRefreshButton';
import { disconnectMetaPlatform, startMetaOAuth } from './integrationsOAuth';
import { ToggleResponseSchema, type IntegrationListRow } from './integrationsSchemas';
import { useIntegrationsLoad } from './useIntegrationsLoad';
import { WhatsAppCloudCard, whatsappCardSubtitle } from './WhatsAppCloudCard';
import { WebChatCard } from './WebChatCard';
import { useWhatsAppIntegrations } from './useWhatsAppIntegrations';

type Row = IntegrationListRow;
type SheetState = IntegrationSheetTarget & { kind: 'meta' | 'whatsapp' };

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
  return row.platform === 'tiktok' || row.platform === 'snapchat';
}

export function IntegrationsScreen({ onRequestLogin, onRequestRegister }: Props) {
  const { tr } = useI18n();
  const nav = useModuleNav();
  const [busyPlatform, setBusyPlatform] = useState<string | null>(null);
  const [busyToggle, setBusyToggle] = useState<{ platform: string; key: 'dm' | 'comments' } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [authGate, setAuthGate] = useState(false);
  const [sheet, setSheet] = useState<SheetState | null>(null);
  const wa = useWhatsAppIntegrations({
    onAuthGate: () => setAuthGate(true),
    onError: (message) => setError(message),
  });
  const { loading, hasLoadedOnce, notice, setNotice, rows, setRows, load } = useIntegrationsLoad({
    tr,
    refreshWhatsApp: wa.refreshWhatsApp,
    activeArea: nav.activeArea,
    areaFocusNonce: nav.areaFocusNonce,
    setError,
    setAuthGate,
  });
  const headerRefreshing = loading && hasLoadedOnce;
  const whatsappInitialLoading = loading && !wa.waStatus;

  async function connectPlatform(platform: 'instagram' | 'facebook') {
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
    const platform = row.platform === 'facebook' ? 'facebook' : 'instagram';
    const accountName =
      row.account?.display_name ||
      row.accounts?.[0]?.display_name ||
      (platform === 'facebook' ? tr('platformFacebook') : tr('platformInstagram'));

    Alert.alert(tr('disconnectAccount'), `${accountName}\n${tr('disconnectAccountConfirm')}`, [
      { text: tr('usersCancel'), style: 'cancel' },
      {
        text: tr('disconnect'),
        style: 'destructive',
        onPress: () => {
          void (async () => {
            setBusyPlatform(row.platform);
            setError(null);
            try {
              await disconnectMetaPlatform(platform);
              await load();
            } catch (err) {
              if (err instanceof ApiError && err.status === 401) setAuthGate(true);
              else setError(tr('integrationsActionError'));
            } finally {
              setBusyPlatform(null);
            }
          })();
        },
      },
    ]);
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
      } else setError(tr('integrationsActionError'));
    } finally {
      setBusyPlatform(null);
    }
  }

  async function setToggle(row: Row, key: 'dm' | 'comments', value: boolean) {
    const previous = defaultToggles(row as IntegrationRow);
    const platform = row.platform === 'facebook' ? 'facebook' : 'instagram';

    if (value === true && !row.connected) {
      setError(tr('commentsBlockerConnectFirst'));
      await connectPlatform(platform);
      return;
    }

    if (key === 'comments' && value === true) {
      const blocker = commentsBlocker(row as IntegrationRow);
      if (blocker === 'missing_comment_permissions' || blocker === 'reauthorization_required') {
        const missing = row.comments_state?.missing_scopes?.filter(Boolean) ?? [];
        setError(
          missing.length
            ? `${tr('commentsBlockerMissingPermissions')} Missing: ${missing.join(', ')}. ${tr('disconnectThenConnectHint')}`
            : `${tr('commentsBlockerMissingPermissions')} ${tr('disconnectThenConnectHint')}`,
        );
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
        await connectPlatform(platform);
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
          setError(`${typeof msg === 'string' && msg.trim() ? msg : tr('integrationsToggleError')} ${tr('disconnectThenConnectHint')}`);
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

  function openMetaSheet(row: Row) {
    const platform = row.platform === 'facebook' ? 'facebook' : 'instagram';
    setSheet({
      kind: 'meta',
      platform,
      title: platformTitle(row),
      subtitle: channelSubtitle(row as IntegrationRow),
    });
  }

  function onSheetDisconnect() {
    const target = sheet;
    setSheet(null);
    if (!target) return;
    if (target.kind === 'whatsapp') {
      Alert.alert(tr('disconnectAccount'), `${target.title}\n${tr('disconnectAccountConfirm')}`, [
        { text: tr('usersCancel'), style: 'cancel' },
        {
          text: tr('disconnect'),
          style: 'destructive',
          onPress: () => void wa.disconnectWhatsApp(load),
        },
      ]);
      return;
    }
    const row = rows.find((r) => r.platform === target.platform);
    if (row) void disconnectPlatform(row);
  }

  const metaRows = rows.filter((row) => row.platform === 'instagram' || row.platform === 'facebook');
  const tiktokRow = rows.find((row) => row.platform === 'tiktok');

  return (
    <ScreenChrome
      title={tr('integrations')}
      subtitle={tr('integrationsSub')}
      headerRight={
        <IntegrationRefreshButton
          onRefresh={() => void load()}
          refreshing={headerRefreshing}
          accessibilityLabel={tr('refreshConnectionStatus')}
        />
      }
    >
      {notice ? <Text style={styles.notice}>{notice}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView contentContainerStyle={styles.list}>
        {metaRows.map((row) => (
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
            onReconcileComments={() => void reconcileComments(row)}
            onConnect={() =>
              void connectPlatform(row.platform === 'facebook' ? 'facebook' : 'instagram')
            }
            onOpenMenu={() => openMetaSheet(row)}
          />
        ))}
        <WhatsAppCloudCard
          status={wa.waStatus}
          loading={whatsappInitialLoading}
          busy={wa.waBusy}
          onRefresh={() => void load()}
          onConnect={() => void wa.connectWhatsApp()}
          onOpenMenu={() =>
            setSheet({
              kind: 'whatsapp',
              platform: 'whatsapp',
              title: tr('platformWhatsApp'),
              subtitle: whatsappCardSubtitle(wa.waStatus, tr('integrationWhatsAppHandle')),
            })
          }
          onEnableAi={(id) => void wa.setWhatsAppAi(id, true, load)}
          onDisableAi={(id) => void wa.setWhatsAppAi(id, false, load)}
          onBusyChange={wa.setWaBusy}
          onError={setError}
          onNotice={setNotice}
        />
        <WebChatCard onError={setError} onNotice={setNotice} />
        {tiktokRow ? (
          <IntegrationChannelCard
            key="tiktok"
            row={tiktokRow as IntegrationRow}
            title={platformTitle(tiktokRow)}
            soon={isComingSoon(tiktokRow)}
            busy={false}
            busyToggleKey={null}
            actionsDisabled
            tr={tr}
            onToggle={() => undefined}
            onReconcileComments={() => undefined}
            onConnect={() => undefined}
            onOpenMenu={() => undefined}
          />
        ) : null}
      </ScrollView>

      <IntegrationAccountSheet
        target={sheet}
        connectedLabel={tr('connected')}
        refreshLabel={tr('integrationRefreshStatus')}
        disconnectLabel={tr('integrationDisconnectAccount')}
        disconnectHint={tr('integrationDisconnectHint')}
        cancelLabel={tr('usersCancel')}
        closeLabel={tr('usersCancel')}
        onRefresh={() => {
          setSheet(null);
          void load();
        }}
        onDisconnect={onSheetDisconnect}
        onClose={() => setSheet(null)}
      />

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
  list: { paddingBottom: 40, gap: 14 },
  notice: { color: colors.accent, marginBottom: spacing.md, fontFamily: fonts.body },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
