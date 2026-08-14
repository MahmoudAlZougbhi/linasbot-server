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

export type ConnectionDisplayStatus = 'connected' | 'needs_reconnect' | 'error' | 'disconnected';

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
    default:
      return tr('commentsBlockerGeneric');
  }
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
  return acc.display_name || acc.username || '';
}

function asPlatform(platform: string): IntegrationPlatform {
  if (platform === 'facebook' || platform === 'whatsapp' || platform === 'tiktok') return platform;
  return 'instagram';
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
  const showToggles = !soon && (platform === 'instagram' || platform === 'facebook') && row.connected;
  const blocker = commentsBlocker(row);
  const needsWebhook = blocker === 'missing_comment_webhook';
  const subtitle = channelSubtitle(row);
  const healthy = row.connected && row.connection_status !== 'error' && row.connection_status !== 'needs_reconnect';

  return (
    <IntegrationCardShell
      platform={platform}
      title={title}
      subtitle={subtitle}
      connected={row.connected}
      soon={soon}
      busy={busy}
      connectLabel={tr('connect')}
      connectedLabel={tr('connected')}
      notConnectedLabel={tr('notConnected')}
      comingSoonLabel={tr('comingSoon')}
      healthLabel={tr('integrationStatusConnected')}
      menuLabel={tr('disconnectAccount')}
      showConnect={!soon && !row.connected}
      showMenu={!soon && row.connected}
      showHealth={!soon && row.connected && healthy}
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
          {blocker ? <Text style={styles.blocker}>{blockerCopy(blocker, tr)}</Text> : null}
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
