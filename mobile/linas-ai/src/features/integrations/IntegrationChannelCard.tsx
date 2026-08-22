import { StyleSheet, Text } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts } from '../../theme';
import {
  ChannelCapabilityToggles,
  type ChannelToggles,
} from './ChannelCapabilityToggles';
import { IntegrationCardShell } from './IntegrationCardShell';
import type { IntegrationAccountDisplay } from './IntegrationAccountSection';
import type { IntegrationPlatform } from './IntegrationPlatformIcon';

export type CommentsState = {
  requested_enabled: boolean;
  permission_present: boolean;
  webhook_subscribed: boolean;
  tenant_action_enabled?: boolean;
  connection_healthy?: boolean;
  live_verified: boolean;
  effective_enabled: boolean;
  missing_scopes?: string[];
  blocker?: string | null;
  blocker_code?: string | null;
  blocker_message?: string | null;
  status?: string;
  last_checked_at?: number;
};

export type IntegrationFeatures = {
  dm_replies: boolean;
  comment_replies: boolean;
};

export type ConnectionDisplayStatus =
  | 'connected'
  | 'needs_reconnect'
  | 'error'
  | 'disconnected'
  | 'connecting'
  | 'permission_required'
  | 'token_expired';

export type IntegrationRow = {
  platform: string;
  label: string;
  connected: boolean;
  coming_soon?: boolean;
  connectable?: boolean;
  toggles?: ChannelToggles;
  comments_blocker?: string;
  comments_state?: CommentsState;
  dm_state?: CommentsState;
  connection_status?: ConnectionDisplayStatus;
  service_diagnostic?: string;
  last_synced_at?: number | null;
  account?: IntegrationAccountDisplay;
  accounts?: IntegrationAccountDisplay[];
  features?: IntegrationFeatures;
};

type Props = {
  row: IntegrationRow;
  title: string;
  soon: boolean;
  busy: boolean;
  busyToggleKey: 'dm' | 'comments' | null;
  actionsDisabled: boolean;
  tr: (key: StringKey) => string;
  onToggle: (key: 'dm' | 'comments', value: boolean) => void;
  onReconcileComments: () => void;
  onConnect: () => void;
  onOpenMenu: () => void;
};

export function defaultToggles(row: IntegrationRow): ChannelToggles {
  return row.toggles ?? { dm: false, comments: false };
}

export function commentsBlocker(row: IntegrationRow): string | null {
  return (
    row.comments_blocker ??
    row.comments_state?.blocker_code ??
    row.comments_state?.blocker ??
    null
  );
}

function blockerCopy(blocker: string, tr: (key: StringKey) => string): string {
  switch (blocker) {
    case 'missing_comment_permissions':
      return tr('commentsBlockerMissingPermissions');
    case 'connect_channel_first':
      return tr('commentsBlockerConnectFirst');
    case 'missing_comment_webhook':
      return tr('commentsBlockerMissingWebhook');
    case 'meta_approval_required':
      return tr('commentsBlockerMetaApproval');
    case 'reauthorization_required':
    case 'connection_unhealthy':
      return tr('commentsBlockerReauthorization');
    case 'tiktok_messaging_pending':
      return tr('tiktokMessagingPending');
    case 'token_expired':
      return tr('integrationStatusTokenExpired');
    case 'missing_dm_permissions':
      return tr('commentsBlockerMissingPermissions');
    case 'asset_action_off':
      return tr('integrationDmActionOff');
    case 'webhook_not_ready':
      return tr('serviceDiagnosticWebhookNotReady');
    case 'missing_scopes':
      return tr('serviceDiagnosticMissingScopes');
    case 'expired_token':
      return tr('serviceDiagnosticExpiredToken');
    case 'credential_unavailable':
      return tr('serviceDiagnosticCredentialUnavailable');
    case 'token_app_mismatch':
    case 'token_profile_mismatch':
      return tr('serviceDiagnosticTokenMismatch');
    default:
      return tr('commentsBlockerGeneric');
  }
}

function serviceDiagnosticCopy(code: string | undefined, tr: (key: StringKey) => string): string | null {
  if (!code) return null;
  return blockerCopy(code, tr);
}

function accountList(row: IntegrationRow): IntegrationAccountDisplay[] {
  if (row.accounts?.length) return row.accounts;
  if (row.account) return [row.account];
  return [];
}

export function channelSubtitle(row: IntegrationRow): string {
  const acc = accountList(row)[0];
  if (!acc) return '';
  if (row.platform === 'instagram') {
    const raw = (acc.username || acc.display_name || '').trim();
    if (!raw) return '';
    const handle = raw.replace(/^@/, '');
    return `@${handle}`;
  }
  if (row.platform === 'tiktok') {
    const handle = (acc.username || acc.display_name || '').trim();
    const name = handle ? (handle.startsWith('@') ? handle : `@${handle.replace(/^@/, '')}`) : acc.display_name || '';
    return name;
  }
  return acc.display_name || acc.username || '';
}

function asPlatform(platform: string): IntegrationPlatform {
  if (platform === 'facebook' || platform === 'whatsapp' || platform === 'tiktok') return platform;
  return 'instagram';
}

function tiktokStatusLabel(
  status: string,
  tr: (key: StringKey) => string,
): string | undefined {
  if (status === 'connecting') return tr('integrationStatusConnecting');
  if (status === 'permission_required') return tr('integrationStatusPermissionRequired');
  if (status === 'token_expired') return tr('integrationStatusTokenExpired');
  if (status === 'error') return tr('integrationStatusError');
  return undefined;
}

export function IntegrationChannelCard({
  row,
  title,
  soon,
  busy,
  busyToggleKey,
  actionsDisabled,
  tr,
  onToggle,
  onReconcileComments,
  onConnect,
  onOpenMenu,
}: Props) {
  const platform = asPlatform(row.platform);
  const tiktok = platform === 'tiktok';
  const status = String(row.connection_status || '');
  const needsReconnect = tiktok && (status === 'token_expired' || status === 'permission_required' || status === 'error');
  const showToggles =
    !soon && (platform === 'instagram' || platform === 'facebook' || tiktok) && row.connected;
  const blocker = commentsBlocker(row);
  const showMetaCapabilityHints = false;
  const dmBlocker = row.dm_state?.blocker_code || row.dm_state?.blocker || null;
  const dmBlockerMessage = row.dm_state?.blocker_message?.trim() || null;
  const serviceDiagnostic = showMetaCapabilityHints ? serviceDiagnosticCopy(row.service_diagnostic, tr) : null;
  const needsWebhook = showMetaCapabilityHints && blocker === 'missing_comment_webhook';
  const subtitle = channelSubtitle(row);
  const lastSync =
    typeof row.last_synced_at === 'number' && row.last_synced_at > 0
      ? `${tr('integrationLastSynced')}: ${new Date(row.last_synced_at * 1000).toLocaleString()}`
      : tiktok && row.connected
        ? tr('tiktokLastSyncNever')
        : '';
  const healthy = row.connected && row.connection_status !== 'error' && row.connection_status !== 'needs_reconnect';
  const statusLabel = tiktok ? tiktokStatusLabel(status, tr) : undefined;

  return (
    <IntegrationCardShell
      platform={platform}
      title={title}
      subtitle={lastSync ? `${subtitle}${subtitle ? '\n' : ''}${lastSync}` : subtitle}
      connected={row.connected}
      soon={soon}
      busy={busy}
      connectLabel={needsReconnect ? tr('integrationReconnect') : tr('connect')}
      connectedLabel={tr('connected')}
      notConnectedLabel={tr('notConnected')}
      comingSoonLabel={tr('comingSoon')}
      statusLabel={statusLabel}
      healthLabel={tr('integrationStatusConnected')}
      menuLabel={tr('disconnectAccount')}
      showConnect={!soon && (!row.connected || needsReconnect)}
      showMenu={!soon && row.connected}
      showHealth={!soon && row.connected && healthy && !needsReconnect}
      onConnect={onConnect}
      onMenu={onOpenMenu}
    >
      {showToggles ? (
        <>
          <ChannelCapabilityToggles
            toggles={defaultToggles(row)}
            busyKey={busyToggleKey}
            disabled={actionsDisabled}
            messagesLabel={tr('integrationToggleMessages')}
            commentsLabel={tr('toggleComments')}
            onToggle={onToggle}
          />
          {showMetaCapabilityHints && blocker ? <Text style={styles.blocker}>{blockerCopy(blocker, tr)}</Text> : null}
          {showMetaCapabilityHints && dmBlocker && !blocker ? (
            <Text style={styles.blocker}>{blockerCopy(String(dmBlocker), tr)}</Text>
          ) : null}
          {showMetaCapabilityHints && dmBlockerMessage ? <Text style={styles.blocker}>{dmBlockerMessage}</Text> : null}
          {serviceDiagnostic ? <Text style={styles.blocker}>{serviceDiagnostic}</Text> : null}
          {showMetaCapabilityHints && row.comments_state?.blocker_message?.trim() ? (
            <Text style={styles.blocker}>{row.comments_state.blocker_message.trim()}</Text>
          ) : null}
          {needsWebhook ? (
            <PrimaryButton
              label={tr('reconcileCommentWebhooks')}
              onPress={onReconcileComments}
              loading={busy}
              disabled={actionsDisabled}
              variant="ghost"
            />
          ) : null}
        </>
      ) : null}
    </IntegrationCardShell>
  );
}

const styles = StyleSheet.create({
  blocker: { color: colors.danger, fontFamily: fonts.body, fontSize: 13 },
});
